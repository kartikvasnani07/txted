
import os
import sys
import json
import time
import re
from pathlib import Path
from datetime import datetime

# curses import - if on windows, use windows-curses package
try:
    import curses
    import curses.ascii
except Exception as e:
    print("Error importing curses:", e)
    print("If you're on Windows: python -m pip install windows-curses")
    sys.exit(1)

try:
    import pyperclip
    CLIP_AVAILABLE = True
except Exception:
    CLIP_AVAILABLE = False

HOME = os.path.expanduser("~")
HISTORY_FILE = os.path.join(HOME, ".cli_text_editor_history.json")

LANG_TO_EXT = {
    "python": ".py", "javascript": ".js", "typescript": ".ts",
    "c/c++": ".c", "java": ".java", "html": ".html", "css": ".css",
    "json": ".json", "xml": ".xml", "bash/sh": ".sh", "markdown": ".md", "text": ".txt"
}
EXT_TO_LANG = {v: k for k, v in LANG_TO_EXT.items()}

PY_KEYWORDS = set((
    "False", "None", "True", "and", "as", "assert", "async", "await",
    "break", "class", "continue", "def", "del", "elif", "else", "except",
    "finally", "for", "from", "global", "if", "import", "in", "is", "lambda",
    "nonlocal", "not", "or", "pass", "raise", "return", "try", "while", "with", "yield"
))

def load_history():
    # maybe empty file, so handle errors, hehe
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []

def save_history(hist):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(hist, f, indent=2)
    except Exception:
        pass

def add_to_history(path):
    path = os.path.abspath(path)
    hist = load_history()
    hist = [h for h in hist if h.get("path") != path] if isinstance(hist, list) and hist and isinstance(hist[0], dict) else []
    if isinstance(hist, list) and hist and isinstance(hist[0], dict):
        hist.insert(0, {"path": path, "last_opened": datetime.now().isoformat()})
    else:
        hist = [path] + [p for p in hist if p != path]
    save_history(hist)

def remove_from_history(index):
    hist = load_history()
    if 0 <= index < len(hist):
        hist.pop(index)
        save_history(hist)

def clear_history():
    save_history([])

# simple undo/redo stack
class UndoStack:
    def __init__(self, maxlen=200):
        self.stack = []
        self.index = -1
        self.maxlen = maxlen

    def push(self, state):
        if self.index < len(self.stack) - 1:
            self.stack = self.stack[:self.index+1]
        self.stack.append(state)
        if len(self.stack) > self.maxlen:
            self.stack.pop(0)
        else:
            self.index += 1

    def can_undo(self):
        return self.index > 0

    def can_redo(self):
        return self.index < len(self.stack) - 1

    def undo(self):
        if self.can_undo():
            self.index -= 1
            return self.stack[self.index]
        return None

    def redo(self):
        if self.can_redo():
            self.index += 1
            return self.stack[self.index]
        return None

# main editor 
class Editor:
    PAIRS = {"{": "}", "[": "]", "(" : ")", "<": ">", '"': '"', "'": "'"}
    OPENERS = set(PAIRS.keys())
    CLOSERS = set(PAIRS.values())

    def __init__(self, stdscr, filename=None, text=None, language=None, read_only=False):
        self.stdscr = stdscr
        self.filename = filename
        self.buffer = (text.splitlines() if text is not None else [""])
        if not self.buffer:
            self.buffer = [""]
        self.language = language or (EXT_TO_LANG.get(Path(filename).suffix, "text") if filename else "text")
        self.read_only = read_only
        self.mode = 'NORMAL'  # NORMAL or INSERT
        self.cursor_y = 0
        self.cursor_x = 0
        self.top_line = 0
        self.left_col = 0
        # initial size from curses
        self.height, self.width = self.stdscr.getmaxyx()
        self.gutter_width = 4
        self.search_pattern = None
        self.search_matches = []
        self.search_index = -1
        self.undo = UndoStack()
        self.undo.push((list(self.buffer), self.cursor_y, self.cursor_x))
        self.modified = False
        self._init_curses()
        self.stdscr.keypad(True)
        # enable mouse events
        curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
        if self.filename:
            add_to_history(self.filename)

    def _init_curses(self):
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)   
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_BLUE)  
        curses.init_pair(3, curses.COLOR_YELLOW, -1) 
        curses.init_pair(4, curses.COLOR_GREEN, -1)  
        curses.init_pair(5, curses.COLOR_MAGENTA, -1) 
        curses.init_pair(6, curses.COLOR_RED, -1)    
        self.c_gutter = curses.color_pair(1)
        self.c_cur = curses.color_pair(2)
        self.c_kw = curses.color_pair(3)
        self.c_str = curses.color_pair(4)
        self.c_com = curses.color_pair(5)
        self.c_num = curses.color_pair(6)
        self.attr_normal = curses.A_NORMAL

    def _calc_gutter(self):
        digits = max(1, len(str(max(1, len(self.buffer)))))
        self.gutter_width = digits + 2

    def _display_filename(self):
        return Path(self.filename).name if self.filename else "[untitled]"

    def _render_line_minimal(self, y, xstart, text):
        if self.language == 'python':
            i = 0
            for m in re.finditer(r'\w+|\W+', text):
                tok = m.group(0)
                try:
                    if tok.isidentifier() and tok in PY_KEYWORDS:
                        self.stdscr.addstr(y, xstart + i, tok, self.c_kw)
                    elif tok.startswith(('"', "'")):
                        self.stdscr.addstr(y, xstart + i, tok, self.c_str)
                    else:
                        self.stdscr.addstr(y, xstart + i, tok, self.attr_normal)
                    i += len(tok)
                except curses.error:
                    break
        else:
            try:
                self.stdscr.addstr(y, xstart, text[:self.width - xstart - 1], self.attr_normal)
            except curses.error:
                pass

    def _render(self):
        self.height, self.width = self.stdscr.getmaxyx()
        try:
            if curses.is_term_resized(self.height, self.width):
                curses.resize_term(self.height, self.width)
                # clear so popup remnants are cleared from screen
                self.stdscr.clear()
        except Exception:
            pass

        self._calc_gutter()
        self.stdscr.erase()
        visible = self.height - 2
        for i in range(visible):
            lineno = self.top_line + i
            y = i
            if lineno >= len(self.buffer):
                continue
            line = self.buffer[lineno]
            gutter = f"{lineno+1}".rjust(self.gutter_width - 2) + " "
            try:
                if lineno == self.cursor_y:
                    self.stdscr.addstr(y, 0, gutter[:self.gutter_width], self.c_gutter | curses.A_BOLD)
                    try:
                        fill = ' ' * (self.width - self.gutter_width)
                        self.stdscr.addstr(y, self.gutter_width, fill, self.c_cur)
                    except curses.error:
                        pass
                    self._render_line_minimal(y, self.gutter_width - self.left_col, line[self.left_col:])
                else:
                    self.stdscr.addstr(y, 0, gutter[:self.gutter_width], self.c_gutter)
                    self._render_line_minimal(y, self.gutter_width - self.left_col, line[self.left_col:])
            except curses.error:
                pass
        # separator
        try:
            self.stdscr.hline(self.height - 2, 0, '-', self.width)
        except curses.error:
            pass
        # status
        fname = self._display_filename()
        mode_tag = f'[{self.mode}]'
        modified = '(modified)' if self.modified else ''
        search_info = ''
        if self.search_pattern:
            search_info = f' /{self.search_pattern} ({len(self.search_matches)}) '
        status = f' {fname}  Ln {self.cursor_y+1},Col {self.cursor_x+1} {modified} {mode_tag} [{self.language}] {search_info}'
        hint = " :help | :w :wq :q! | i Insert | s Save | o SaveAs | x Save+Exit | q Quit | c Copy "
        status_line = status + ' ' * max(0, self.width - len(status) - len(hint)) + hint
        try:
            self.stdscr.addstr(self.height - 1, 0, status_line[:self.width-1], curses.A_REVERSE)
        except curses.error:
            pass
        # cursor pos adjuster
        screen_y = self.cursor_y - self.top_line
        screen_x = self.cursor_x - self.left_col + self.gutter_width
        visible_h = self.height - 2
        if screen_y < 0:
            self.top_line = self.cursor_y
            screen_y = 0
        elif screen_y >= visible_h:
            self.top_line = self.cursor_y - visible_h + 1
            screen_y = self.cursor_y - self.top_line
        max_top = max(0, len(self.buffer) - visible_h)
        if self.top_line > max_top:
            self.top_line = max_top
            screen_y = self.cursor_y - self.top_line
        if screen_x < self.gutter_width:
            self.left_col = self.cursor_x
            screen_x = self.cursor_x - self.left_col + self.gutter_width
        elif screen_x >= self.width:
            self.left_col = self.cursor_x - (self.width - self.gutter_width - 2)
            screen_x = self.cursor_x - self.left_col + self.gutter_width
        try:
            self.stdscr.move(screen_y, screen_x)
        except curses.error:
            pass
        self.stdscr.refresh()

    def _snapshot(self):
        self.undo.push((list(self.buffer), self.cursor_y, self.cursor_x))

    def _insert_char(self, ch):
        line = self.buffer[self.cursor_y]
        if ch in self.PAIRS:
            pair = self.PAIRS[ch]
            self.buffer[self.cursor_y] = line[:self.cursor_x] + ch + pair + line[self.cursor_x:]
            self.cursor_x += 1
        elif ch in self.CLOSERS:
            if self.cursor_x < len(line) and line[self.cursor_x] == ch:
                self.cursor_x += 1
                return
            else:
                self.buffer[self.cursor_y] = line[:self.cursor_x] + ch + line[self.cursor_x:]
                self.cursor_x += 1
        else:
            self.buffer[self.cursor_y] = line[:self.cursor_x] + ch + line[self.cursor_x:]
            self.cursor_x += len(ch)
        self.modified = True

    def _backspace(self):
        if self.cursor_x > 0:
            line = self.buffer[self.cursor_y]
            self.buffer[self.cursor_y] = line[:self.cursor_x-1] + line[self.cursor_x:]
            self.cursor_x -= 1
            self.modified = True
        elif self.cursor_y > 0:
            prev = self.buffer[self.cursor_y-1]
            cur = self.buffer.pop(self.cursor_y)
            old_x = len(prev)
            self.buffer[self.cursor_y-1] = prev + cur
            self.cursor_y -= 1
            self.cursor_x = old_x
            self.modified = True

    def _delete(self):
        line = self.buffer[self.cursor_y]
        if self.cursor_x < len(line):
            self.buffer[self.cursor_y] = line[:self.cursor_x] + line[self.cursor_x+1:]
            self.modified = True
        elif self.cursor_y < len(self.buffer)-1:
            nxt = self.buffer.pop(self.cursor_y+1)
            self.buffer[self.cursor_y] = line + nxt
            self.modified = True

    def _enter(self):
        line = self.buffer[self.cursor_y]
        left = line[:self.cursor_x]
        right = line[self.cursor_x:]
        m = re.match(r'^(\s*)', left)
        indent = m.group(1) if m else ''
        extra = ''
        if left.rstrip().endswith((':','{','(','[','<')):
            extra = '    '
        self.buffer[self.cursor_y] = left
        self.buffer.insert(self.cursor_y+1, indent+extra+right)
        self.cursor_y += 1
        self.cursor_x = len(indent+extra)
        self.modified = True

    # cursor moves
    def _move_left(self):
        if self.cursor_x > 0:
            self.cursor_x -= 1
        elif self.cursor_y > 0:
            self.cursor_y -= 1
            self.cursor_x = len(self.buffer[self.cursor_y])

    def _move_right(self):
        if self.cursor_x < len(self.buffer[self.cursor_y]):
            self.cursor_x += 1
        elif self.cursor_y < len(self.buffer)-1:
            self.cursor_y += 1
            self.cursor_x = 0

    def _move_up(self):
        if self.cursor_y > 0:
            self.cursor_y -= 1
            self.cursor_x = min(self.cursor_x, len(self.buffer[self.cursor_y]))

    def _move_down(self):
        if self.cursor_y < len(self.buffer)-1:
            self.cursor_y += 1
            self.cursor_x = min(self.cursor_x, len(self.buffer[self.cursor_y]))

    def _page_up(self):
        jump = max(1, (self.height-2)//2)
        self.cursor_y = max(0, self.cursor_y - jump)
        self.cursor_x = min(self.cursor_x, len(self.buffer[self.cursor_y]))

    def _page_down(self):
        jump = max(1, (self.height-2)//2)
        self.cursor_y = min(len(self.buffer)-1, self.cursor_y + jump)
        self.cursor_x = min(self.cursor_x, len(self.buffer[self.cursor_y]))

    def _home(self):
        self.cursor_x = 0

    def _end(self):
        self.cursor_x = len(self.buffer[self.cursor_y])

    def _move_to_mouse(self, mx, my):
        lineno = self.top_line + my
        lineno = max(0, min(lineno, len(self.buffer)-1))
        col = self.left_col + (mx - self.gutter_width)
        col = max(0, min(col, len(self.buffer[lineno])))
        self.cursor_y = lineno
        self.cursor_x = col

    # file opts.
    def _save(self, ask_filename=False):
        if ask_filename or not self.filename:
            suggested = f"untitled{LANG_TO_EXT.get(self.language, '.txt')}"
            prompt_text = f"Save As (default: {suggested}): "
            fname = self._prompt(prompt_text).strip() or suggested
            if not fname:
                return False
            self.filename = fname
        try:
            with open(self.filename, "w", encoding="utf-8") as f:
                f.write("\n".join(self.buffer))
            self.modified = False
            add_to_history(self.filename)
            return True
        except Exception as e:
    
            try:
                self._prompt_msg(f"Save error: {e}")
            except Exception:
                pass
            return False

    def _copy(self):
        txt = "\n".join(self.buffer)
        if CLIP_AVAILABLE:
            try:
                pyperclip.copy(txt)
                self._prompt_msg("Copied to clipboard.")
                return
            except Exception:
                pass
        self._prompt_msg("Clipboard not available. Showing content.")
        self._show_popup(txt)

    def _prompt(self, prompt_text):
        # recomputing size in case terminal resized before prompting
        self.height, self.width = self.stdscr.getmaxyx()
        try:
            if curses.is_term_resized(self.height, self.width):
                curses.resize_term(self.height, self.width)
                self.stdscr.clear()
        except Exception:
            pass

        curses.curs_set(1)
        curses.noecho()
        win_h = 3
        win_w = max(40, min(self.width-4, len(prompt_text) + 60))
        starty = max(0, (self.height - win_h) // 2)
        startx = max(0, (self.width - win_w) // 2)
        win = curses.newwin(win_h, win_w, starty, startx)
        win.keypad(True)
        win.box()
        try:
            win.addstr(1, 1, prompt_text)
        except curses.error:
            pass
        win.refresh()

        buf = []
        pos = 0
        win.timeout(100)  # allow periodic checks for resize
        while True:
            try:
                ch = win.getch()
            except Exception:
                ch = -1
            if ch == -1:
                # timeout, check if terminal resized
                h, w = self.stdscr.getmaxyx()
                if h != self.height or w != self.width:
                    self.height, self.width = h, w
                    try:
                        if curses.is_term_resized(self.height, self.width):
                            curses.resize_term(self.height, self.width)
                    except Exception:
                        pass
                    win_w = max(40, min(self.width-4, len(prompt_text) + 60))
                    starty = max(0, (self.height - win_h) // 2)
                    startx = max(0, (self.width - win_w) // 2)
                    try:
                        win.erase()
                        win.refresh()
                    except Exception:
                        pass
                    win = curses.newwin(win_h, win_w, starty, startx)
                    win.keypad(True)
                    win.box()
                    try:
                        win.addstr(1, 1, prompt_text)
                    except curses.error:
                        pass
                    try:
                        win.addstr(1, len(prompt_text) + 1, ''.join(buf)[:win_w - len(prompt_text) - 3])
                    except curses.error:
                        pass
                    win.refresh()
                continue
            # handle enter
            if ch in (curses.ascii.NL, curses.ascii.CR):
                break
            if ch == 27:
                buf = []
                break
            if ch == curses.KEY_RESIZE:
                h, w = self.stdscr.getmaxyx()
                self.height, self.width = h, w
                try:
                    if curses.is_term_resized(self.height, self.width):
                        curses.resize_term(self.height, self.width)
                except Exception:
                    pass
                win_w = max(40, min(self.width-4, len(prompt_text) + 60))
                starty = max(0, (self.height - win_h) // 2)
                startx = max(0, (self.width - win_w) // 2)
                win.erase()
                win.refresh()
                win = curses.newwin(win_h, win_w, starty, startx)
                win.keypad(True)
                win.box()
                try:
                    win.addstr(1, 1, prompt_text)
                except curses.error:
                    pass
                try:
                    win.addstr(1, len(prompt_text) + 1, ''.join(buf)[:win_w - len(prompt_text) - 3])
                except curses.error:
                    pass
                win.refresh()
                continue
            # backspace
            if ch in (curses.KEY_BACKSPACE, 127, 8):
                if pos > 0:
                    buf.pop(pos-1)
                    pos -= 1
                try:
                    win.addstr(1, len(prompt_text) + 1, ' ' * (win_w - len(prompt_text) - 3))
                    win.addstr(1, len(prompt_text) + 1, ''.join(buf)[:win_w - len(prompt_text) - 3])
                except curses.error:
                    pass
                win.move(1, len(prompt_text) + 1 + pos)
                win.refresh()
                continue
            # left/right
            if ch == curses.KEY_LEFT:
                if pos > 0: pos -= 1
                win.move(1, len(prompt_text) + 1 + pos); win.refresh(); continue
            if ch == curses.KEY_RIGHT:
                if pos < len(buf): pos += 1
                win.move(1, len(prompt_text) + 1 + pos); win.refresh(); continue

            if 0 <= ch <= 255:
                c = chr(ch)
                if c.isprintable():
                    buf.insert(pos, c)
                    pos += 1
                    try:
                        win.addstr(1, len(prompt_text) + 1, ''.join(buf)[:win_w - len(prompt_text) - 3])
                    except curses.error:
                        pass
                    win.move(1, len(prompt_text) + 1 + pos)
                    win.refresh()
                    continue
            # ignore other keys
            continue

        try:
            res = ''.join(buf)
        except Exception:
            res = ''
        curses.curs_set(0)
        curses.echo()
        self.stdscr.touchwin(); self.stdscr.refresh()
        return res

    def _prompt_msg(self, msg, wait=1):
        # message windows also should adapt to terminal size changes
        self.height, self.width = self.stdscr.getmaxyx()
        try:
            if curses.is_term_resized(self.height, self.width):
                curses.resize_term(self.height, self.width)
                self.stdscr.clear()
        except Exception:
            pass

        win_h, win_w = 3, min(self.width-4, max(40, len(msg)+4))
        starty = max(0, (self.height - win_h)//2)
        startx = max(0, (self.width - win_w)//2)
        win = curses.newwin(win_h, win_w, starty, startx)
        win.box()
        try:
            win.addstr(1,2, msg[:win_w-4])
        except curses.error:
            pass
        win.refresh(); time.sleep(wait)
        self.stdscr.touchwin(); self.stdscr.refresh()

    def _show_popup(self, text):
        # making popup size dynamic every time
        self.height, self.width = self.stdscr.getmaxyx()
        try:
            if curses.is_term_resized(self.height, self.width):
                curses.resize_term(self.height, self.width)
                self.stdscr.clear()
        except Exception:
            pass

        lines = text.splitlines() or [""]
        h = min(self.height-4, len(lines)+2)
        w = min(self.width-4, max(40, max((len(l) for l in lines[:h-2]), default=40)))
        starty = max(0, (self.height - h)//2)
        startx = max(0, (self.width - w)//2)
        win = curses.newwin(h, w, starty, startx)
        win.box()
        for i, ln in enumerate(lines[:h-2]):
            try:
                win.addstr(1+i, 1, ln[:w-2])
            except curses.error:
                pass
        win.refresh(); win.getch()
        self.stdscr.touchwin(); self.stdscr.refresh()
    def _find_all(self, pattern):
        self.search_pattern = pattern
        self.search_matches = []
        try:
            cre = re.compile(pattern)
        except re.error:
            cre = None
        for i, ln in enumerate(self.buffer):
            if cre:
                for m in cre.finditer(ln):
                    self.search_matches.append((i, m.start(), m.end()-m.start()))
            else:
                idx = ln.find(pattern)
                if idx != -1:
                    self.search_matches.append((i, idx, len(pattern)))
        self.search_index = 0 if self.search_matches else -1
        if self.search_index >= 0:
            y,x,l = self.search_matches[self.search_index]
            self.cursor_y, self.cursor_x = y, x
            self._prompt_msg(f"Found {len(self.search_matches)} matches. Jumped to first.", wait=1)

    def _next_match(self):
        if not self.search_matches:
            self._prompt_msg('No matches'); return
        self.search_index = (self.search_index + 1) % len(self.search_matches)
        y,x,l = self.search_matches[self.search_index]; self.cursor_y, self.cursor_x = y, x

    def _prev_match(self):
        if not self.search_matches:
            self._prompt_msg('No matches'); return
        self.search_index = (self.search_index - 1) % len(self.search_matches)
        y,x,l = self.search_matches[self.search_index]; self.cursor_y, self.cursor_x = y, x

    # command_mode ':'
    def _command_mode(self):
        cmd = self._prompt(':')
        if not cmd: return
        cmd = cmd.strip()
        if cmd == 'u':
            s = self.undo.undo()
            if s:
                self.buffer, self.cursor_y, self.cursor_x = s[0], s[1], s[2]
            return
        if cmd == 'r':
            s = self.undo.redo()
            if s:
                self.buffer, self.cursor_y, self.cursor_x = s[0], s[1], s[2]
            return
        if cmd in ('help','h'):
            self._show_help(); return
        if cmd == 'w':
            self._save(ask_filename=False); return
        if cmd == 'wq':
            ok = self._save(ask_filename=False)
            if ok: raise SystemExit
            return
        if cmd == 'q!':
            raise SystemExit
        if cmd == 'q':
            if not self.modified:
                raise SystemExit
            else:
                self._prompt_msg('Unsaved changes. Use x to save+exit or q! to force quit', wait=2)
                return
        if cmd.startswith('/'):
            self._find_all(cmd[1:]); return
        if cmd.startswith('e '):
            fname = cmd[2:].strip()
            if not os.path.exists(fname):
                self._prompt_msg('File not found'); return
            try:
                with open(fname, 'r', encoding='utf-8') as f:
                    txt = f.read()
                self.buffer = txt.splitlines() or ['']
                self.filename = fname
                self.language = EXT_TO_LANG.get(Path(fname).suffix, 'text')
                self.cursor_y = 0; self.cursor_x = 0; self.modified = False
                add_to_history(fname)
            except Exception as e:
                self._prompt_msg(f'Error opening: {e}')
            return
        if cmd == 'ls':
            hist = load_history(); self._show_popup('\n'.join([h['path'] for h in hist[:50]] or ['(empty)'])); return
        if cmd == 'clearhist':
            clear_history(); self._prompt_msg('History cleared'); return
        self._prompt_msg('Unknown command: ' + cmd)

    def _show_help(self):
        help_text = """
CLI TEXT EDITOR - HELP MANUAL
================================

INTRODUCTION
------------
This is a simple curses-based code/text editor inspired by Vim.
It supports NORMAL and INSERT modes, syntax highlighting (basic),
search, undo/redo, history, and more.

BASIC USAGE
-----------
- NORMAL mode: default when editor starts
- INSERT mode: press 'i' to type text
- ESC: return to NORMAL mode

NORMAL MODE COMMANDS
--------------------
i        - switch to INSERT mode
s        - save file
o        - save as (prompt for filename)
x        - save and exit
q        - quit (without saving if no changes)
c        - copy buffer to clipboard (if available)
:        - enter command line

INSERT MODE
-----------
- Regular typing, Backspace, Enter with auto-indent and pairs
- ESC returns to NORMAL mode
- ':' just types a colon, does not open command box

COMMAND-LINE (type ':' in NORMAL mode)
--------------------------------------
:help      - open this help manual
:w         - save
:wq        - save and quit
:q         - quit (fails if unsaved changes)
:q!        - force quit discarding changes
:u         - undo last change
:r         - redo last undo
:/pattern  - search text
:e <file>  - open another file
:ls        - show recent file history
:clearhist - clear recent file history

NAVIGATION
----------
Arrow keys   - move cursor
PageUp/PageDn- half-page scroll
Home/End     - jump to line start/end
Mouse click  - move cursor

SEARCH
------
- Use :/pattern to find matches
- n to go to next match, N for previous

UNDO/REDO
---------
- :u to undo
- :r to redo

NOTES
-----
- Editor resizes automatically with terminal
- Status bar shows filename, cursor pos, mode
- Copy requires 'pyperclip' installed
- History saved in ~/.cli_text_editor_history.json

EXIT HELP
---------
Press Esc, q, or x to close this manual and return to editing.
"""

        lines = help_text.strip("\n").splitlines()
        pos = 0
        while True:
            self.stdscr.erase()
            h, w = self.stdscr.getmaxyx()
            max_lines = h - 1
            for i in range(max_lines):
                if pos + i < len(lines):
                    ln = lines[pos+i]
                    try:
                        self.stdscr.addstr(i, 0, ln[:w-1])
                    except curses.error:
                        pass
            # status line
            status = f"HELP - {pos+1}/{len(lines)} (Esc/q/x to exit, Up/Down to scroll)"
            try:
                self.stdscr.addstr(h-1, 0, status[:w-1], curses.A_REVERSE)
            except curses.error:
                pass
            self.stdscr.refresh()

            ch = self.stdscr.getch()
            if ch in (27, ord('q'), ord('x')):  # Esc, q, x
                break
            elif ch == curses.KEY_DOWN and pos < len(lines)-max_lines:
                pos += 1
            elif ch == curses.KEY_UP and pos > 0:
                pos -= 1
            elif ch == curses.KEY_NPAGE:  # PageDown
                pos = min(len(lines)-max_lines, pos+max_lines)
            elif ch == curses.KEY_PPAGE:  # PageUp
                pos = max(0, pos-max_lines)


    # main run loop - adding resize check here as well
    def run(self):
        while True:
            # checking if window size changed then updating the size acc.
            try:
                if curses.is_term_resized(self.height, self.width):
                    self.height, self.width = self.stdscr.getmaxyx()
                    curses.resize_term(self.height, self.width)
                    self.stdscr.clear()
                    try:
                        self.stdscr.erase()
                        self.stdscr.refresh()
                        self.stdscr.touchwin()
                    except Exception:
                        pass
            except Exception:
                try:
                    self.height, self.width = self.stdscr.getmaxyx()
                except Exception:
                    pass

            self._render()
            try:
                ch = self.stdscr.getch()
            except KeyboardInterrupt:
                if self.mode == 'INSERT':
                    self.mode = 'NORMAL'; continue
                if not self.modified:
                    break
                ans = self._prompt('Unsaved changes. Save? (y/N): ')
                if ans.lower().startswith('y'):
                    self._save(ask_filename=False); break
                else:
                    break
            if ch == -1: continue

            if ch == curses.KEY_MOUSE:
                try:
                    _, mx, my, _, bstate = curses.getmouse()
                    if bstate & (curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED):
                        if my < self.height - 2:
                            self._move_to_mouse(mx, my)
                    continue
                except curses.error:
                    continue

            if ch == ord('n') and self.mode == 'NORMAL':
                self._next_match(); continue
            if ch == ord('N') and self.mode == 'NORMAL':
                self._prev_match(); continue
                
            if self.mode == 'NORMAL':
                
                if ch == ord('s'):
                    self._save(ask_filename=False); continue
                if ch == ord('o'):
                    self._save(ask_filename=True); continue
                if ch == ord('x'):
                    ok = self._save(ask_filename=False)
                    if ok:
                        self.stdscr.erase()
                        self.stdscr.refresh()

                        return self.filename, "\n".join(self.buffer), self.modified
                    continue
                if ch == ord('q'):
                    self.stdscr.erase()
                    self.stdscr.refresh()
                    return self.filename, "\n".join(self.buffer), False
                if ch == ord('c'):
                    self._copy(); continue
                if ch == ord('i'):
                    self.mode = 'INSERT'; continue
                if ch == ord(':'):
                    self._command_mode()
                    continue
                if ch in (curses.KEY_LEFT, curses.KEY_RIGHT, curses.KEY_UP, curses.KEY_DOWN,
                          curses.KEY_NPAGE, curses.KEY_PPAGE, curses.KEY_HOME, curses.KEY_END):
                    pass

            if ch == 27:
                if self.mode == 'INSERT':
                    self.mode = 'NORMAL'; continue
                
            if ch == curses.KEY_LEFT:
                self._move_left(); continue
            if ch == curses.KEY_RIGHT:
                self._move_right(); continue
            if ch == curses.KEY_UP:
                self._move_up(); continue
            if ch == curses.KEY_DOWN:
                self._move_down(); continue
            if ch == curses.KEY_NPAGE:
                self._page_down(); continue
            if ch == curses.KEY_PPAGE:
                self._page_up(); continue
            if ch == curses.KEY_HOME:
                self._home(); continue
            if ch == curses.KEY_END:
                self._end(); continue
        
            if ch in (curses.ascii.NL, curses.ascii.CR):
                if self.mode != 'INSERT':
                    self._prompt_msg("Press 'i' to enter insert mode.")
                else:
                    self._snapshot(); self._enter(); self.undo.push((list(self.buffer), self.cursor_y, self.cursor_x))
                continue
            
            if ch in (curses.KEY_BACKSPACE, 127, 8):
                if self.mode != 'INSERT':
                    self._prompt_msg("Press 'i' to enter insert mode.")
                else:
                    self._snapshot(); self._backspace(); self.undo.push((list(self.buffer), self.cursor_y, self.cursor_x))
                continue
            
            if ch == curses.KEY_DC:
                if self.mode != 'INSERT':
                    self._prompt_msg("Press 'i' to enter insert mode.")
                else:
                    self._snapshot(); self._delete(); self.undo.push((list(self.buffer), self.cursor_y, self.cursor_x))
                continue
    
            if 0 <= ch <= 255 and (chr(ch).isprintable() or ch == 9):
                if self.mode != 'INSERT':
                    self._prompt_msg("Press 'i' to enter insert mode.")
                else:
                    self._snapshot()
                    if ch == 9:
                        self._insert_char('    ')
                    else:
                        self._insert_char(chr(ch))
                    self.undo.push((list(self.buffer), self.cursor_y, self.cursor_x))
                continue
            

# wrapper and menu
def run_editor_with_filename(filename, text, language=None, read_only=False):
    # clearing terminal before launching editor
    try:
        if os.name == 'nt':
            os.system('cls')
        else:
            os.system('clear')
    except Exception:
        pass

    def _c(stdscr):
        ed = Editor(stdscr, filename=filename, text=text, language=language, read_only=read_only)
        return ed.run()
    try:
        result = curses.wrapper(_c)
        # clearing terminal after editor returns to avoid leftover garbage
        try:
            if os.name == 'nt':
                os.system('cls')
            else:
                os.system('clear')
        except Exception:
            pass
        return result
    except SystemExit:
        try:
            if os.name == 'nt':
                os.system('cls')
            else:
                os.system('clear')
        except Exception:
            pass
        return filename, "\n".join(text.splitlines() if text else []), False
    except Exception as e:
        print('Error launching editor:', e)
        raise

def prompt_input(msg):
    try:
        return input(msg).strip()
    except KeyboardInterrupt:
        return ''

def choose_language_prompt():
    print("\nChoose language / extension (or press Enter for text):")
    keys = list(LANG_TO_EXT.keys())
    for i, k in enumerate(keys, 1):
        print(f"{i}) {k} ({LANG_TO_EXT[k]})")
    choice = prompt_input("Choice number: ")
    if not choice:
        return "text"
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(keys):
            return keys[idx]
    except Exception:
        pass
    return "text"

def menu_main():
    print("Notes: Use 'i' to insert, ESC to normal. In NORMAL mode: s Save, o SaveAs, x Save+Exit, q Quit (discard), c Copy, : commands")
    while True:
        print("\n=== CLI Code/Text Editor ===")
        print("1) New File")
        print("2) Open/Import File")
        print("3) History")
        print("4) Quit")
        print("5) Clear Terminal") 
        choice = prompt_input("Choose option: ")
        if choice == "1":
            lang = choose_language_prompt()
            ext = LANG_TO_EXT.get(lang, ".txt")
            suggested = f"untitled{ext}"
            print(f"New file will default to: {suggested}. You can Save As later.")
            run_editor_with_filename(None, "", language=lang, read_only=False)
            try:
                if os.name == 'nt':
                    os.system('cls')
                else:
                    os.system('clear')
            except Exception:
                pass
        elif choice in ("2"):
            path = prompt_input("Enter file path to open: ")
            if not path:
                print("Cancelled."); continue
            if not os.path.exists(path):
                create = prompt_input("File doesn't exist. Create new? (y/N): ")
                if create.lower().startswith("y"):
                    open(path, "w", encoding="utf-8").close()
                else:
                    continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
            except Exception as e:
                print("Error opening file:", e); continue
            ext = Path(path).suffix
            lang = EXT_TO_LANG.get(ext, "text")
            run_editor_with_filename(path, text, language=lang, read_only=True)
            try:
                if os.name == 'nt':
                    os.system('cls')
                else:
                    os.system('clear')
            except Exception:
                pass

        elif choice == "3":
            history_menu()
        elif choice == "4":
            # clearing screen completely before exit
            try:
                if os.name == 'nt':
                    os.system('cls')
                else:
                    os.system('clear')
            except Exception:
                pass
            break

        elif choice == "5":
            try:
                if os.name == 'nt':
                    os.system('cls')
                else:
                    os.system('clear')
            except Exception:
                pass
        else:
            print("Invalid choice")

def history_menu():
    while True:
        hist = load_history()
        print("\n--- History ---")
        if not hist:
            print("(empty)"); return
        for i, h in enumerate(hist):
            if isinstance(h, dict):
                p = h.get("path"); t = h.get("last_opened", "")[:19].replace("T", " ")
                print(f"{i+1}) {p}  (last opened: {t})")
            else:
                print(f"{i+1}) {h}")
        print("--------------------------")
        print("a) Open by number")
        print("b) Delete entry by number")
        print("c) Clear history")
        print("x) Back")
        print("--------------------------")
        choice = prompt_input("Choice: ")
        print("--------------------------")
        if choice == "a":
            n = prompt_input("Enter number to open: ")
            try:
                idx = int(n) - 1
                path = hist[idx]["path"] if isinstance(hist[idx], dict) else hist[idx]
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        text = f.read()
                    ext = Path(path).suffix
                    lang = EXT_TO_LANG.get(ext, "text")
                    run_editor_with_filename(path, text, language=lang, read_only=True)
                    try:
                        if os.name == 'nt':
                            os.system('cls')
                        else:
                            os.system('clear')
                    except Exception:
                        pass
                else:
                    print("File not found on disk.")

            except Exception:
                print("Invalid index.")
        elif choice == "b":
            n = prompt_input("Enter number to delete from history: ")
            try:
                idx = int(n) - 1
                remove_from_history(idx)
                print("Deleted.")
            except Exception:
                print("Invalid index.")
        elif choice == "c":
            confirm = prompt_input("Clear history? (y/N): ")
            if confirm.lower().startswith("y"):
                clear_history(); print("Cleared.")
            else:
                print("Cancelled.")
        elif choice == "x":
            break
        else:
            print("Invalid.")


