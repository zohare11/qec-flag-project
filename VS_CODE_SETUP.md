# Mac / VS Code setup from your existing qram_project

## 1. Put the new folder beside the old one

Download `qec_flag_project.zip` and double-click it in Finder. It expands to `qec_flag_project`.

Select the expanded folder and press Command+C. Press Command+Shift+H to open your Home folder. Press Command+V. You should now have:

```text
Home/
    qram_project/
    qec_flag_project/
```

Do not put the new folder inside `qram_project`, and do not delete or rename the old project. If you already have a folder with the same new name, stop rather than merging experiments without checking their contents.

## 2. Create an isolated environment using your existing Python installation

Use the existing VS Code terminal where your prompt starts `(qram_env)`. A terminal command belongs after a shell prompt such as `%`, not inside a Python `>>>` prompt. Type `exit()` first if you are inside Python.

Run these lines in the SAME terminal. Do not close it until the block is finished; `BASE_PYTHON` is a temporary shell variable.

```bash
BASE_PYTHON="$(python -c 'import sys; print(sys._base_executable)')"
deactivate
cd ~/qec_flag_project
"$BASE_PYTHON" -m venv --prompt qec_flag_env .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The first line remembers the base Python used by your working QRAM environment. Deactivation does not uninstall anything. The new environment does not copy your QRAM packages and does not change the old environment.

Commands that only create a folder or assign a variable can finish without printing anything. A prompt returning is normal. Stop if a command prints an error instead of continuing through the remaining lines.

Now check:

```bash
pwd
python -c "import sys; print(sys.executable)"
```

The first output should end in `/qec_flag_project`. The second should end in `/qec_flag_project/.venv/bin/python`. The prompt should normally start `(qec_flag_env)`; the executable path is the decisive check.

If your old environment is not active, use the Python interpreter you used for it, or locate it from the old workspace's Python interpreter selection. Do not substitute a very old macOS system Python. The pinned dependencies require Python 3.11 or newer; the reference run used 3.13.5.

## 3. Open the new folder in its own VS Code window

Choose File > New Window. In the new window choose File > Open Folder. Select `qec_flag_project` in your Home folder and open it. The Explorer sidebar should show `run_pipeline.py`, `qecflag`, `tests`, `configs`, and `requirements.txt`.

This folder already IS the project. There is no separate project-creation wizard to run and no need to recreate the Python files manually.

Install the Microsoft Python extension if it is missing: Command+Shift+X opens Extensions; search for `Python` and choose the Microsoft extension. You do not need Jupyter or a code-runner extension for this project.

Open `run_pipeline.py` once. Press Command+Shift+P and run `Python: Select Interpreter`. Select the interpreter inside this project's `.venv`. If not listed, use `Enter interpreter path` and browse to:

```text
/Users/YOUR_MAC_USERNAME/qec_flag_project/.venv/bin/python
```

Use the actual path printed by the earlier check; YOUR_MAC_USERNAME is a placeholder, not text to paste literally. Hidden folders can be shown in Finder with Command+Shift+period.

## 4. Open the new window's terminal

Choose Terminal > New Terminal. Explicitly activate the environment:

```bash
cd ~/qec_flag_project
source .venv/bin/activate
python run_pipeline.py doctor
```

The doctor should show `inside_virtual_environment: true`, the new executable path, NumPy 2.3.5, and pytest 9.0.2. Do not use the editor's Run button for the pipeline; use the commands below, which specify the desired configuration and output directory.

## 5. Run tests, then the smoke pipeline

```bash
python -m pytest -q
```

Expected result: `397 passed`. The runtime will vary. If a test fails, stop before training; retain the full failure output.

```bash
python run_pipeline.py all --config configs/smoke.json --out runs/smoke
```

This repeats the tests, performs the exhaustive physics checks, trains one short policy, evaluates every baseline, runs noisy diagnostics, and writes reports. Expected physics counts are 360 ideal schedules, 96 certified schedules, and 33,840 dense single-fault cross-checks. Rejected unsafe schedules are intentional.

## 6. Run the full configured experiment

```bash
python run_pipeline.py all --config configs/full.json --out runs/full
```

This executes three training seeds. Do not alter the configuration to force a positive result. Both positive and negative comparisons are informative.

Open `runs/full/summary.md` from Explorer. Open `runs/full/evaluation.json` for detailed baseline comparisons and `runs/full/noise.json` for finite-shot intervals. The provided `reference_runs` folder contains the runs executed in the development workspace; it is not your new run output.

An existing nonempty output directory is protected. To rerun:

```bash
python run_pipeline.py all --config configs/full.json --out runs/full_2
```

## 7. Return later

Reopen the `qec_flag_project` folder in VS Code, open Terminal > New Terminal, then:

```bash
cd ~/qec_flag_project
source .venv/bin/activate
```

There is no need to recreate or reinstall the environment every session. To return to the QRAM project, reopen its folder and activate its environment instead; the projects stay independent.

## Troubleshooting

**`can't open file run_pipeline.py`:** Run `pwd` and `ls`. You are probably outside the new project folder, or the ZIP expanded into another nested folder. `run_pipeline.py` and `requirements.txt` must be directly inside the folder you opened.

**`No module named numpy` or `pytest`:** Activate `.venv`, verify `sys.executable`, and run `python -m pip install -r requirements.txt`. Use `python -m pip`, not an unrelated `pip` command.

**Old environment in the prompt:** Run `deactivate`, then `cd ~/qec_flag_project` and `source .venv/bin/activate`. Also fix VS Code's selected interpreter.

**`BASE_PYTHON` is empty:** It was set in another terminal session, or `python` was not your working old interpreter. Return to the old environment and repeat the capture line, keeping that terminal open for environment creation.

**`python`/`deactivate` not found:** Your old environment is not active. Open the working QRAM terminal or activate that environment first. Alternatively use the full interpreter path shown in its VS Code interpreter selector.

**Installation reports incompatible Python:** Use Python 3.11 or newer. The existing working 3.13 installation is sufficient; there is no need to upgrade to the newest Python.

**Existing output directory:** Choose a new `--out` path. Do not delete old evidence just to rerun.

**Checkpoint/config mismatch:** Use the same config and run directory for train/evaluate/noise. Changed physics/configuration requires a new run and new training.

**You interrupted a command:** Control+C stops it. The logs remain. Individual stages can be run using README commands. Training starts again from its seed rather than resuming optimizer state.

**Learned policy loses to a baseline:** That is a result, not an installation failure. Never change the correctness tests or remove a stronger baseline to turn it into a win.
