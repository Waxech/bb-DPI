# bb-DPI

A modern GUI for GoodbyeDPI with a minimalist and easy-to-use UI.

## Features
- **Modern UI**: Borderless window with custom shadows and sleek animations.
- **System Tray**: Runs in the background with a system tray icon for easy access.
- **One-Click Toggle**: Start and stop the background process easily.
- **Stand-Alone**: Can be compiled to a single executable.

## Prerequisites
- Windows 10 or 11
- Python 3.10+ (if running from source)

## Installation & Running from Source

1. Clone the repository:
   ```bash
   git clone https://github.com/username/bb-DPI.git
   cd bb-DPI
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the application:
   ```bash
   python app.py
   ```

## Building the Executable

To build a standalone executable that doesn't require Python to be installed:

1. Install PyInstaller:
   ```bash
   pip install pyinstaller
   ```
2. Build the app using the provided spec file:
   ```bash
   pyinstaller app.spec
   ```
3. The compiled `.exe` will be located in the `dist` folder.

## Note on GoodbyeDPI
This application is a GUI wrapper. You need to have the GoodbyeDPI executable (`goodbyedpi.exe`) in the correct path or bundled with the app as expected by the script.

## License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
