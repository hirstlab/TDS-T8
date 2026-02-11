# Building T8 DAQ System Executable

This guide explains how to build a standalone Windows executable (`.exe`) for the T8 DAQ System using PyInstaller.

## Quick Start (Current Environment)

If you already have Python/Anaconda set up and just want to build:

```cmd
# Activate your virtual environment
.venv\Scripts\activate

# Install PyInstaller (if not already installed)
pip install pyinstaller

# Build the executable
pyinstaller t8_daq_system.spec --clean

# Find the executable in:
dist\T8_DAQ_System.exe
```

## Recommended: Pure Python Setup

For better results (smaller size, faster builds), we recommend using **pure Python** instead of Anaconda:

### Benefits of Pure Python

| Metric | Anaconda | Pure Python | Improvement |
|--------|----------|-------------|-------------|
| Executable Size | 150-250 MB | 80-120 MB | 40% smaller |
| Build Time | 3-5 minutes | 2-3 minutes | 40% faster |
| Startup Time | 3-5 seconds | 2-3 seconds | 30% faster |
| DLL Count | 40-60 DLLs | 5-15 DLLs | 70% fewer |
| Maintainability | Complex | Simple | Easier debugging |

**Important**: All project dependencies are available on PyPI - **no conda-specific packages** are required!

---

## Pure Python Installation Guide (Windows)

### Step 1: Install Python 3.11

1. **Download Python 3.11.7** from the official website:
   ```
   https://www.python.org/downloads/release/python-3117/
   ```
   Direct link: [python-3.11.7-amd64.exe](https://www.python.org/ftp/python/3.11.7/python-3.11.7-amd64.exe)

2. **Run the installer** with these CRITICAL settings:

   ```
   ☑ Install launcher for all users (recommended)
   ☑ Add python.exe to PATH    <-- VERY IMPORTANT!
   ```

   Click **"Customize installation"**

3. **Optional Features** (check all):
   ```
   ☑ Documentation
   ☑ pip
   ☑ tcl/tk and IDLE    <-- REQUIRED for tkinter GUI
   ☑ Python test suite
   ☑ py launcher
   ```

4. **Advanced Options**:
   ```
   ☑ Install for all users
   ☑ Add Python to environment variables
   ☑ Precompile standard library
   Installation path: C:\Program Files\Python311  (recommended)
   ```

5. **Verify installation**:
   ```cmd
   # Open NEW command prompt (to load updated PATH)
   python --version
   # Should show: Python 3.11.7

   # Verify tkinter (critical for GUI)
   python -m tkinter
   # Should show a small Tcl/Tk window
   ```

### Step 2: Create Pure Python Virtual Environment

1. **Navigate to project**:
   ```cmd
   cd C:\Users\IGLeg\PycharmProjects\TDS-T8
   ```

2. **Backup old environment** (optional):
   ```cmd
   rename .venv .venv_anaconda_backup
   ```

3. **Create new venv with pure Python**:
   ```cmd
   # Create virtual environment
   python -m venv .venv

   # Activate it
   .venv\Scripts\activate

   # Verify it's pure Python (not Anaconda)
   where python
   # Should show: C:\Users\IGLeg\PycharmProjects\TDS-T8\.venv\Scripts\python.exe
   # NOT: C:\Users\IGLeg\anaconda3\python.exe
   ```

### Step 3: Install Dependencies

```cmd
# Make sure .venv is activated
.venv\Scripts\activate

# Upgrade pip
python -m pip install --upgrade pip

# Install project dependencies
pip install -r requirements.txt

# Install PyInstaller
pip install pyinstaller

# Verify installations
pip list
# Should show: labjack-ljm, matplotlib, numpy, pyserial, pyvisa, pyvisa-py, pyinstaller
```

### Step 4: Test Application

**Before building, always test that the application runs correctly:**

```cmd
# Run the application
python t8_daq_system\main.py
```

**Expected behavior**:
- ✓ GUI window appears
- ✓ No import errors
- ✓ Matplotlib plots render
- ✓ Hardware connects (if available) or shows "not found" messages

If errors occur, fix them **before** building the executable.

### Step 5: Build the Executable

```cmd
# Clean previous builds
rmdir /s /q build dist

# Build with pure Python
pyinstaller t8_daq_system.spec --clean
```

**Watch the build output for**:
```
✓ Found tcl86t.dll
✓ Found tk86t.dll
✓ Found libffi-8.dll
✓ Found LabJack LJM: C:\Program Files\...
Total binaries to bundle: 5-15  (pure Python has fewer!)
```

**Build result**:
```
dist\T8_DAQ_System.exe  (approximately 80-120 MB)
```

### Step 6: Test the Executable

```cmd
# Run the executable
cd dist
T8_DAQ_System.exe
```

**Test checklist**:
- [ ] Application starts within 5 seconds
- [ ] GUI renders correctly
- [ ] Thermocouple readings update (if hardware connected)
- [ ] Live plot scrolls with data
- [ ] Data logging creates CSV files
- [ ] Config file loads correctly
- [ ] Application exits cleanly

---

## Troubleshooting

### Issue: "NameError: name '__file__' is not defined"

**Fixed in latest version**. The spec file now uses `SPECPATH` instead of `__file__`.

### Issue: "tkinter module not found"

**Cause**: TCL/TK not installed with Python

**Solution**:
```cmd
# Verify tkinter works in development
python -m tkinter

# If it fails, reinstall Python with tcl/tk option checked
```

### Issue: "LabJack LJM DLL not found"

**Cause**: LabJack LJM driver not installed

**Solution**:
1. Download from: https://labjack.com/support/software/installers/ljm
2. Install the driver
3. Rebuild executable: `pyinstaller t8_daq_system.spec --clean`

### Issue: "Executable crashes immediately"

**Solution**: Enable debug mode

1. Edit `t8_daq_system.spec`, line 268:
   ```python
   console=True,  # Changed from False
   ```

2. Rebuild:
   ```cmd
   pyinstaller t8_daq_system.spec --clean
   ```

3. Run from command prompt to see errors:
   ```cmd
   cd dist
   T8_DAQ_System.exe
   ```

4. Check console output for error messages

### Issue: "Executable too large (>150 MB)"

This usually indicates you're using Anaconda. Pure Python builds should be 80-120 MB.

**Solution**:
1. Verify you're using pure Python: `where python` should NOT show `anaconda3`
2. If using Anaconda, follow **Step 2** above to create pure Python venv
3. Rebuild

### Issue: "DLL load failed"

**Cause**: Missing DLLs

**Solution**:
1. Check build output for "⚠ Warning: XXX.dll not found"
2. Common missing DLLs:
   - `libffi-8.dll` - Reinstall Python
   - `tcl86t.dll`, `tk86t.dll` - Reinstall Python with tcl/tk
   - `ljm.dll` - Install LabJack LJM driver

---

## Distribution

### Packaging for End Users

1. **Test on clean machine**:
   - Windows 10/11 without Python installed
   - Verifies true portability

2. **Create distribution package**:
   ```cmd
   mkdir T8_DAQ_System_Release
   copy dist\T8_DAQ_System.exe T8_DAQ_System_Release\
   copy README.md T8_DAQ_System_Release\
   copy LICENSE T8_DAQ_System_Release\
   mkdir T8_DAQ_System_Release\config
   copy t8_daq_system\config\sensor_config.json T8_DAQ_System_Release\config\
   ```

3. **Create README for users**:
   Create `T8_DAQ_System_Release\REQUIREMENTS.txt`:
   ```
   T8 DAQ System - User Requirements

   REQUIRED SOFTWARE:
   1. LabJack LJM Driver (for hardware support)
      Download: https://labjack.com/support/software/installers/ljm

   2. National Instruments VISA Driver (for Keysight power supply)
      Download: https://www.ni.com/en-us/support/downloads/drivers/download.ni-visa.html

   HARDWARE CONNECTIONS:
   - LabJack T8: USB connection
   - XGS-600 Controller: USB-to-Serial or RS-232
   - Keysight N5761A: USB or GPIB-USB adapter

   FIRST RUN:
   1. Install required drivers
   2. Connect hardware
   3. Run T8_DAQ_System.exe
   4. Use "Practice Mode" to test without hardware
   ```

4. **Compress for distribution**:
   ```cmd
   powershell Compress-Archive -Path T8_DAQ_System_Release -DestinationPath T8_DAQ_System_v1.0.zip
   ```

---

## Build Comparison: Anaconda vs Pure Python

### With Anaconda

**Pros**:
- Familiar environment if already using Anaconda
- Works with current setup

**Cons**:
- Large executables (150-250 MB)
- Complex DLL management (2+ directories)
- Slower builds (3-5 minutes)
- Slower startup (3-5 seconds)
- Hardcoded paths may break on different machines

### With Pure Python (Recommended)

**Pros**:
- Smaller executables (80-120 MB) - **40% reduction**
- Simple DLL management (1 directory)
- Faster builds (2-3 minutes) - **40% faster**
- Faster startup (2-3 seconds) - **30% faster**
- More portable
- Easier debugging

**Cons**:
- Requires one-time setup (~30 minutes)
- Need to create new virtual environment

**Verdict**: Pure Python is recommended for production builds.

---

## Advanced Options

### Multi-File Distribution (Smaller Size)

For even smaller size, use directory-based distribution:

1. Edit `t8_daq_system.spec`, line 254:
   ```python
   exe = EXE(
       pyz,
       a.scripts,
       exclude_binaries=True,  # Changed from False
       # ... rest of configuration ...
   )
   ```

2. Add at end of spec file:
   ```python
   coll = COLLECT(
       exe,
       a.binaries,
       a.zipfiles,
       a.datas,
       strip=False,
       upx=True,
       upx_exclude=[],
       name='T8_DAQ_System',
   )
   ```

3. Build: `pyinstaller t8_daq_system.spec --clean`
4. Result: `dist\T8_DAQ_System\` folder with exe + DLLs

**Benefits**:
- Smaller total size (~60-80 MB)
- Faster startup
- Easier to update individual DLLs

**Drawbacks**:
- Must distribute entire folder
- Users see multiple files

### UPX Compression

For additional size reduction:

1. Download UPX from: https://github.com/upx/upx/releases
2. Extract to `C:\UPX` (or add to PATH)
3. UPX is already enabled in the spec file (`upx=True`)
4. Build: `pyinstaller t8_daq_system.spec --clean`

**Benefits**:
- 30-40% smaller DLLs
- No functionality changes

**Drawbacks**:
- Slightly slower startup (decompression overhead)
- Some antivirus software may flag UPX-compressed files

---

## Continuous Integration (Optional)

To automate builds with GitHub Actions:

Create `.github/workflows/build.yml`:

```yaml
name: Build Executable

on:
  release:
    types: [created]

jobs:
  build:
    runs-on: windows-latest

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python 3.11
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install pyinstaller

    - name: Build executable
      run: |
        pyinstaller t8_daq_system.spec --clean

    - name: Upload artifact
      uses: actions/upload-artifact@v3
      with:
        name: T8_DAQ_System.exe
        path: dist/T8_DAQ_System.exe
```

This automatically builds the executable when you create a new release on GitHub.

---

## Support

For issues or questions:

1. **Build errors**: Enable debug mode (see Troubleshooting section)
2. **Hardware issues**: Check driver installation and connections
3. **General questions**: Open an issue on the GitHub repository

**Important Files**:
- `t8_daq_system.spec` - PyInstaller configuration
- `requirements.txt` - Python dependencies
- `BUILDING.md` - This file
- `README.md` - Project overview
