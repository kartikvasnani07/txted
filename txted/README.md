TXTed – A Command-Line Text Editor
==================================

TXTed is a lightweight, terminal-based text editor written in Python using the curses library. 
It was created with the goal of building a practical editor that is easy to use, 
while also serving as a project to understand how text editors work internally. 
Unlike large IDEs or complex editors, TXTed focuses on simplicity, clarity, and 
portability. It is designed for anyone who wants to quickly edit text from the 
command line or learn about text editing software at a deeper level.

-------------------------------------------------------------------------------
Project Structure
-------------------------------------------------------------------------------
Your installed package will follow this structure:

    project/
    │
    ├── txted/
    │   ├── __init__.py
    │   ├── __main__.py
    │   └── editor.py
    │
    ├── README.md
    ├── pyproject.toml
    ├── LICENSE
    └── .gitignore

-------------------------------------------------------------------------------
Installation
-------------------------------------------------------------------------------
TXTed can be installed directly from PyPI. Ensure you have Python 3.8 or newer.

1. From PyPI (recommended):
   pip install txted

   After installation, simply type:
   txted
   to launch the editor.

2. From TestPyPI (for trial testing):
   pip install -i https://test.pypi.org/simple/ txted

3. From source (developer installation):
   Clone this repository and install locally:
       git clone https://github.com/kartikvasnani07/txted.git
       cd txted
       pip install -e .

Dependencies
------------
All dependencies are handled automatically during installation, but for reference:

- Python 3.8+
- curses (built-in on Linux/macOS, use `windows-curses` on Windows)
- pyperclip (for clipboard support)
- setuptools (for building/installing)

-------------------------------------------------------------------------------
Usage
-------------------------------------------------------------------------------

Youtube Video URL (It's not recommended to rely upon this completely) : https://youtu.be/KNgttW1L3sU

When you launch TXTed, the main menu is displayed with the following options:

1) New File          → Start editing a new empty file
2) Open/Import File  → Open an existing file for editing
3) History           → View recently opened files
4) Clear Terminal    → Clear the terminal screen
5) Quit              → Exit the editor

The editor has two modes of operation:

- NORMAL mode: For navigation and commands
- INSERT mode: For typing text

Switch to INSERT mode by pressing "i". Return to NORMAL mode by pressing "Esc".

In NORMAL mode:
- s → Save
- o → Save As
- x → Save and Exit
- q → Quit (discard changes)
- c → Copy buffer to clipboard (if pyperclip is available)
- : → Enter command mode (similar to Vim)

Command mode supports:
- :help → Show the manual in a separate read-only window
- :w → Save
- :wq → Save and quit
- :q → Quit if no changes
- :q! → Force quit without saving
- :u → Undo
- :r → Redo
- :/pattern → Search
- :e filename → Open another file
- :ls → Show history
- :clearhist → Clear history

Other features include:
- Undo/Redo functionality
- Simple syntax highlighting for Python
- Mouse support for cursor movement
- Line numbers and status bar
- Automatic window resizing
- Auto-indentation and matching pairs in INSERT mode

-------------------------------------------------------------------------------
Why TXTed is Useful
-------------------------------------------------------------------------------

TXTed is not designed to replace full-featured editors like VS Code, Sublime, or Vim. 
Its main purpose is to provide a clean and minimal text editing environment in the terminal. 
It is especially useful for students and developers who want to understand how editors 
handle cursor movement, input, rendering, and file management. TXTed also provides 
practical functionality, such as maintaining file history, search, undo/redo, and 
clipboard integration, which makes it usable as a lightweight daily tool.

By combining these features into a compact package, TXTed shows how much can be achieved 
with Python and curses, while also serving as a hands-on learning project.

-------------------------------------------------------------------------------
Development and Contributing
-------------------------------------------------------------------------------

Developers can run the editor in development mode with:

    python -m txted

Contributions are welcome. Focus is on keeping the code clear and readable, while 
gradually improving features. Bug reports, new ideas, and documentation improvements 
are all encouraged. Pull requests should use descriptive commit messages and maintain 
compatibility with Python 3.8+.

-------------------------------------------------------------------------------
Publishing to PyPI
-------------------------------------------------------------------------------
For maintainers: new versions can be published by incrementing the version in pyproject.toml
and running:

    python -m build
    python -m twine upload dist/*

This makes the latest release instantly available via pip install txted.
