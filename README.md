# PyFTMS - Bluetooth Fitness Machine Service async client library

**PyFTMS** is a Python client library for the **FTMS** service, which is a standard for fitness equipment with a Bluetooth interface. **Bleak** is used as the Bluetooth library. Currently four main types of fitness machines are supported:
 1. **Treadmill**
 2. **Cross Trainer** (Elliptical Trainer)
 3. **Rower** (Rowing Machine)
 4. **Indoor Bike** (Spin Bike)

**Step Climber** and **Stair Climber** machines are **not supported** due to incomplete protocol information and low popularity.

This fork publishes production-ready fixes used by the forked Home Assistant FTMS
integration. The corresponding fork release for this branch is `v0.4.15+mw.5`.

## Requirments

1. `bleak`
2. `bleak-retry-connector`

## Install it from PyPI

```bash
pip install pyftms
```

## Install the forked release

```bash
pip install "pyftms @ git+https://github.com/michaelw/python-pyftms.git@v0.4.15+mw.5"
```

## Usage

Please read the fork README and source on
[GitHub](https://github.com/michaelw/python-pyftms).
