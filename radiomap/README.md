# radiomap

Predicted 5.8 GHz radio maps and relay link tables, and tools to check them against measurements. The predictions come from the RadioLunaDiff models in [lunar-mesh-env](https://github.com/anderspearson206/lunar-mesh-env). Outputs go into the terrain folder (`../terrain` on the laptop, `~/terrain` on the cars).

| File | What it does |
|---|---|
| `rm_generate.py` | Radio maps for a BS at any cell (`<site>_rm58_{nn_pmnet,nn}@<col>_<row>.npy`). The dashboard runs it on **Move BS**. Needs the lunar-mesh-env venv (torch, diffusers) |
| `rm_colab_bundle.py` | Packs the model code + site files into `rm_colab_<site>.zip` for the notebook |
| `rm_linktab_colab.ipynb` | Colab GPU notebook: a map with the transmitter at every drivable cell → `<site>_linktab_{nn_pmnet,nn}.npz` (~84 MB, git-ignored), used by the relay brain |
| `linktab_reciprocity.py` | How much `a→b` and `b→a` disagree in a link table, and how much that moves relay choices |
| `relay_replay.py` | Feeds a recorded explorer track through `relay_brain` and plots what a relay would have done |
| `radio_map.py` | Plots measured coverage from `coverage*.csv` |

```bash
~/Documents/lunar-mesh-env/.venv/Scripts/python.exe radiomap/rm_generate.py --site fountain --bs 10,-20
python radiomap/rm_colab_bundle.py --site fountain     # upload the zip + pretrained_models_network.zip to MyDrive/rm_linktab
python radiomap/linktab_reciprocity.py --site fountain --out bs_reports/reciprocity
python radiomap/relay_replay.py bs_reports/<session> --explorer 57936 --site fountain [--dropout 120:200]
python radiomap/radio_map.py bs_reports/<session>/coverage.csv
```
