"""
plan_runner.py - run a prepared experiment plan (analysis/waypoint_selection/plans/*.json) from the BS.

A plan has two or more variants (e.g. "naive" and "radio_map"); each variant gives every role
("rover1", "rover2") a list of steps:
    {"drive": [[x, y], ...], "label": "..."}   drive to the first point (A* from where the rover is), then
                                               along the points as given; sent with BSCore.send_route; done
                                               when the rover reports nav=done for that route
    {"wait": seconds, "label": "..."}          stay put this long
All roles start at the same moment (Run). The runner only sends routes the dashboard could send by
hand, so the usual rules hold: the rover drives only while RB is held (or with "Drive without RB"),
LB takes over, Stop / STOP ALL / releasing RB stop it.

    runner = PlanRunner(core)
    runner.start(plan, 'radio_map', {'rover1': '57936', 'rover2': '54272'})
    runner.tick()            # call regularly (the dashboard does, with its refresh timer)
    runner.abort()

Plan file format "rover-plan/1" (written by example.py and multi_agent_detour.py):
    {"format": "rover-plan/1", "name", "title", "kind", "site", "bs_xy", "start_xy", "speed_mps",
     "margin_R_db", "roles": {"rover1": "explorer", ...},
     "variants": {"naive": {"label", "steps": {"rover1": [...], ...}, "predicted": {...}}, ...}}
"""

import glob
import json
import math
import os
import time

FORMAT = 'rover-plan/1'
PLAN_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'analysis',
                                         'waypoint_selection', 'plans'))
AT_START_M = 3.0          # a rover this close to the plan's start counts as at the start
DONE_GRACE_S = 5.0        # nav=done this long after the ack counts even if the rover was never seen moving
FAILED = ('stopped_off_route', 'stopped_bs', 'no_node')


def list_plans(plan_dir=PLAN_DIR):
    """[(name, path)] of the plan files in plan_dir that use FORMAT."""
    out = []
    for p in sorted(glob.glob(os.path.join(plan_dir, '*.json'))):
        try:
            with open(p) as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        if d.get('format') == FORMAT:
            out.append((d.get('name') or os.path.basename(p)[:-5], p))
    return out


def load_plan(path):
    with open(path) as f:
        d = json.load(f)
    if d.get('format') != FORMAT:
        raise ValueError(f"{path}: not a {FORMAT} plan")
    return d


def step_text(step):
    if 'wait' in step:
        return f"wait {step['wait']:.0f} s" + (f" ({step['label']})" if step.get('label') else '')
    return f"drive {route_len(step['drive']):.0f} m" + (f" ({step['label']})" if step.get('label') else '')


def route_len(pts):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))


class PlanRunner:
    def __init__(self, core):
        self.core = core
        self.plan = None
        self.variant = None
        self.assign = {}            # role -> node
        self.phase = 'idle'         # idle | staging | running | done | aborted
        self.t0 = None
        self.roles = {}             # role -> {'steps', 'i', 'since', 'cmd', 'state', 'note'}
        self.message = ''

    # ------------------------------------------------------------------ control
    def _marker(self, text):
        try:
            self.core.add_marker(text)
        except Exception:
            pass

    def stage(self, plan, assign, speed=None):
        """Drive every assigned rover to the plan's start point."""
        steps = {role: [{'drive': [plan['start_xy']], 'label': 'to the start'}] for role in assign}
        self._begin(plan, None, assign, steps, 'staging', speed)
        self._marker(f"plan-{plan['name']}-to-start")

    def start(self, plan, variant, assign, speed=None):
        """Run a variant: every role starts its steps now."""
        v = plan['variants'][variant]
        missing = [r for r in v['steps'] if r not in assign or not assign[r]]
        if missing:
            raise ValueError(f"no rover chosen for {', '.join(missing)}")
        if len(set(assign[r] for r in v['steps'])) < len(v['steps']):
            raise ValueError("each role needs a different rover")
        self._begin(plan, variant, assign, {r: v['steps'][r] for r in v['steps']}, 'running', speed)
        self._marker(f"plan-{plan['name']}-{variant}-start")

    def _begin(self, plan, variant, assign, steps, phase, speed):
        self.plan, self.variant, self.assign = plan, variant, dict(assign)
        self.speed = float(speed or plan.get('speed_mps', 0.5))
        self.phase, self.t0, self.message = phase, time.time(), ''
        self.roles = {r: {'steps': list(s), 'i': 0, 'since': None, 'cmd': None, 'state': 'pending', 'note': ''}
                      for r, s in steps.items()}

    def abort(self):
        if self.phase in ('staging', 'running'):
            nodes = [self.assign[r] for r in self.roles if self.assign.get(r)]
            self.core.stop_routes(nodes, f"abort plan {self.plan['name']}")
            self._marker(f"plan-{self.plan['name']}-{self.variant or 'start'}-abort")
            self.phase = 'aborted'

    # ------------------------------------------------------------------ stepping
    def tick(self, now=None):
        if self.phase not in ('staging', 'running'):
            return
        now = now or time.time()
        for role, st in self.roles.items():
            for _ in range(len(st['steps']) + 1):         # a finished step starts the next one right away
                i = st['i']
                self._tick_role(role, st, now)
                if st['i'] == i:
                    break
        if all(st['state'] in ('finished', 'failed') for st in self.roles.values()):
            failed = [r for r, st in self.roles.items() if st['state'] == 'failed']
            what = 'start reached' if self.phase == 'staging' else 'done'
            self.phase = 'done' if not failed else 'aborted'
            self.message = (f"{what}" if not failed else f"stopped: {', '.join(failed)} failed")
            self._marker(f"plan-{self.plan['name']}-{self.variant or 'start'}-{'end' if not failed else 'failed'}")

    def _tick_role(self, role, st, now):
        if st['state'] in ('finished', 'failed', 'paused'):
            return
        if st['i'] >= len(st['steps']):
            st['state'] = 'finished'
            return
        step = st['steps'][st['i']]
        node = self.assign[role]
        if st['since'] is None:                                  # entering this step
            st['since'] = now
            if 'drive' in step:
                err = self._send(node, step['drive'])
                if err:
                    st['state'], st['note'] = 'failed', err
                    self.core.stop_routes([n for n in self.assign.values() if n], 'plan step failed')
                    return
                st['cmd'] = (self.core.routes.get(node) or {}).get('cmd')
            st['state'] = 'running'
            if self.phase == 'running':
                self._marker(f"plan-{role}-{st['i'] + 1}-{'wait' if 'wait' in step else 'drive'}")
        if 'wait' in step:
            if now - st['since'] >= float(step['wait']):
                self._next(st)
            return
        status = self.core.rover_status.get(node) or {}
        nc, nav = status.get('nc'), str(status.get('nav', ''))
        if st['cmd'] is None or not isinstance(nc, float) or nc < st['cmd']:
            st['note'] = 'route sent, waiting for the rover to take it'
            return
        if st.get('acked') is None:
            st['acked'] = now
        if nav != 'done':
            st['moved'] = True
        # right after the ack the status can still say done for the previous route: accept done only
        # once the rover was seen on this one, or after DONE_GRACE_S (a leg too short to see)
        if nav == 'done' and (st.get('moved') or now - st['acked'] > DONE_GRACE_S):
            self._next(st)
        elif nav in FAILED:
            st['state'], st['note'] = 'paused', f"rover reports {nav}; plan paused for this rover"
        else:
            prog = f" {status.get('ni', 0):.0f}/{status.get('np', 0):.0f} m" if status.get('np') else ''
            st['note'] = f"{nav}{prog}"

    def _next(self, st):
        st['i'] += 1
        st['since'] = None
        st['cmd'] = None
        st['note'] = ''
        st['acked'] = None
        st['moved'] = False

    def _send(self, node, pts):
        """A* (the dashboard's planner) only from where the rover is to the step's first point, then the
        plan's own points: they already follow the drive area the plan was made for, and A* over the
        whole drivable mask could cut through cells outside it between widely spaced points."""
        import numpy as np
        lead, err = self.core.plan_route(node, [list(pts[0])])
        if lead is None:
            return err or 'could not plan the route'
        route = np.vstack([np.asarray(lead, float), np.asarray(pts[1:], float).reshape(-1, 2)])
        return self.core.send_route(node, route, self.speed)

    def resume(self, role):
        """Retry the current step of a paused role (after the rover was put back on track)."""
        st = self.roles.get(role)
        if st and st['state'] == 'paused':
            st['since'], st['state'], st['note'], st['acked'], st['moved'] = None, 'pending', '', None, False

    # ------------------------------------------------------------------ display
    def status_lines(self, now=None):
        if self.plan is None:
            return []
        now = now or time.time()
        head = {'staging': 'driving to the start', 'running': f"running {self.variant}",
                'done': self.message or 'done', 'aborted': self.message or 'aborted', 'idle': ''}[self.phase]
        lines = [f"<b>{self.plan.get('title', self.plan['name'])}</b>: {head}"
                 + (f", {now - self.t0:.0f} s" if self.t0 and self.phase in ('staging', 'running') else '')]
        for role, st in self.roles.items():
            node = self.assign.get(role, '?')
            n = len(st['steps'])
            if st['i'] < n:
                step = st['steps'][st['i']]
                left = ''
                if 'wait' in step and st['since'] is not None:
                    left = f", {max(0.0, float(step['wait']) - (now - st['since'])):.0f} s left"
                cur = f"step {st['i'] + 1}/{n}: {step_text(step)}{left}"
            else:
                cur = 'finished'
            color = {'failed': '#c62828', 'paused': '#ef6c00', 'finished': '#2e7d32'}.get(st['state'], '#1565c0')
            lines.append(f"{role} ({node}): <span style='color:{color}'>{cur}</span>"
                         + (f" - {st['note']}" if st['note'] else ''))
        return lines

    @staticmethod
    def at_start(core, plan, node):
        """Distance [m] of a rover from the plan's start, or None without a map position."""
        pose = core.map_pose(node)
        if pose is None:
            return None
        return math.hypot(pose[0] - plan['start_xy'][0], pose[1] - plan['start_xy'][1])
