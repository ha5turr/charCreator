# -*- coding: utf-8 -*-
"""
WoW: Forever (Classic+) — автоматическое создание персонажа.
GUI-настройки + бот: клики в долях от размера окна клиента,
детект экрана по пикселям, релог по таймеру, ретраи при ошибке.
"""
import ctypes
import json
import os
import random
import re
import sys
import threading
import time
import traceback
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

# DPI-awareness до импорта GUI/скриншотов — иначе координаты поплывут на scaled-дисплеях
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import pyautogui
import pygetwindow as pgw
from PIL import ImageGrab

pyautogui.FAILSAFE = True  # экстренная остановка: мышь в левый верхний угол экрана
pyautogui.PAUSE = 0.05

APP_NAME = "WoW Forever — Автосоздание персонажа"
APP_VERSION = "0.1.0"
SETTINGS_FILE = "wow_char_auto_settings.json"
LOG_FILE = "wow_char_auto_log.txt"

CLASSES = ["Воин", "Охотник", "Маг", "Разбойник", "Жрец",
           "Чернокнижник", "Паладин", "Друид", "Шаман"]

# ---------------------------------------------------------------------------
# Справочник рас/классов/внешности (WoW: Forever, Classic+, клиент 1.60.1).
# ПРОВЕРЕНО НА ЖИВОМ КЛИЕНТЕ: все 10 рас × оба пола сняты скриншотами
# (съёмка 2026-11-17, разрешение 2560x1440).
# Классы — по официальным данным Forever (6 новых сочетаний: человек-охотник,
# гном-жрец, дворф-шаман, тролль-чернокнижник, орк-маг, отрекшийся-паладин;
# у Небеснорождённых за Альянс — маг, за Орду — шаман).
# "ystart" — Y-координата (доля окна) первого слайдера внешности.
# У нежити панель без иконок вкладок, поэтому слайдеры начинаются выше.
# ---------------------------------------------------------------------------
def _r(label, classes, male_features, ystart=0.2833, female_features=None):
    return {
        "label": label,
        "classes": classes,
        "ystart": ystart,
        "features": {
            "Мужской": male_features,
            "Женский": female_features if female_features else list(male_features),
        },
    }

RACES = {
    "Альянс": [
        _r("Человек",
           ["Воин", "Охотник", "Разбойник", "Жрец", "Маг", "Чернокнижник",
            "Паладин"],
           ["Цвет кожи", "Лицо", "Прическа", "Цвет волос", "Цвет глаз",
            "Брови", "Форма лица"]),
        _r("Дворф",
           ["Воин", "Охотник", "Разбойник", "Жрец", "Паладин", "Шаман"],
           ["Цвет кожи", "Лицо", "Прическа", "Цвет волос", "Цвет глаз"]),
        _r("Ночной эльф",
           ["Воин", "Охотник", "Разбойник", "Жрец", "Друид"],
           ["Цвет кожи", "Лицо", "Прическа", "Цвет волос", "Цвет глаз"],
           female_features=["Цвет кожи", "Лицо", "Прическа", "Цвет волос",
                            "Брови"]),
        _r("Гном",
           ["Воин", "Разбойник", "Жрец", "Маг", "Чернокнижник"],
           ["Цвет кожи", "Лицо", "Прическа", "Цвет волос", "Брови"],
           female_features=["Цвет кожи", "Лицо", "Прическа", "Цвет волос",
                            "Цвет глаз"]),
        _r("Небеснорождённый",
           ["Воин", "Охотник", "Разбойник", "Друид", "Маг"],
           ["Цвет кожи", "Лицо", "Прическа", "Цвет волос", "Уши",
            "Цвет глаз", "Вид бровей"]),
    ],
    "Орда": [
        _r("Орк",
           ["Воин", "Охотник", "Маг", "Разбойник", "Чернокнижник", "Шаман"],
           ["Цвет кожи", "Лицо", "Прическа", "Цвет волос", "Цвет глаз"]),
        _r("Нежить",
           ["Воин", "Разбойник", "Жрец", "Маг", "Чернокнижник", "Паладин"],
           ["Цвет кожи", "Лицо", "Прическа", "Цвет волос",
            "Особенности лица", "Челюсть", "Сияние глаз"],
           ystart=0.2208),
        _r("Таурен",
           ["Воин", "Охотник", "Друид", "Шаман"],
           ["Цвет кожи", "Лицо", "Волосы", "Цвет глаз"]),
        _r("Тролль",
           ["Воин", "Охотник", "Разбойник", "Жрец", "Маг", "Чернокнижник",
            "Шаман"],
           ["Цвет кожи", "Лицо", "Прическа", "Цвет волос", "Цвет глаз"]),
        _r("Небеснорождённый",
           ["Воин", "Охотник", "Разбойник", "Друид", "Шаман"],
           ["Цвет кожи", "Лицо", "Прическа", "Цвет волос", "Уши",
            "Цвет глаз", "Вид бровей"]),
    ],
}

RESOLUTIONS = ["1280x720", "1600x900", "1920x1080", "2560x1440"]

DEFAULTS = {
    "resolution": "2560x1440",
    "attempt_min": 10, "attempt_max": 25,
    "firstname": "", "lastname": "",
    "faction": "Орда", "race": "Нежить",
    "gender": "Мужской", "class": "Чернокнижник",
    "appearance": {},
    "relog_enabled": True, "relog_min": 20, "relog_max": 40,
    "has_other_server_chars": False,
    "stop_on_success": True,
    "test_mode": False,
    "simple_mode": False,
    "debug_shots": True,
}

NAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁё]{2,12}$")


def type_text(text):
    """Посимвольный Unicode-ввод без раскладки клавиатуры и буфера обмена."""
    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                    ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                    ("dwExtraInfo", ctypes.c_size_t)]

    class _INPUT_DATA(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT),
                    ("padding", ctypes.c_byte * (16 + 2 * ctypes.sizeof(ctypes.c_void_p)))]

    class _INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("data", _INPUT_DATA)]

    user32 = ctypes.windll.user32
    user32.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(_INPUT), ctypes.c_int]
    user32.SendInput.restype = ctypes.c_uint
    for char in text:
        for flags in (0x0004, 0x0004 | 0x0002):  # KEYEVENTF_UNICODE + KEYUP
            key = _KEYBDINPUT(0, ord(char), flags, 0, 0)
            event = _INPUT(type=1, data=_INPUT_DATA(ki=key))
            array = (_INPUT * 1)(event)
            if user32.SendInput(1, array, ctypes.sizeof(_INPUT)) != 1:
                raise RuntimeError("Windows не приняла Unicode-ввод имени.")
            time.sleep(0.06)
        time.sleep(0.06)

INSTRUCTION = """ИНСТРУКЦИЯ

1. Запусти игру и зайди на аккаунт до экрана создания персонажа.
2. Игра обязательно в ОКОННОМ режиме (не полный экран), окно развернуто
   и не перекрыто другими окнами.
3. В игре выставь разрешение, совпадающее с выбранным в программе
   (программа кликает пропорционально размеру окна, но совпадение
   разрешения повышает точность).
4. Заполни настройки: имя/фамилия (русские или латинские буквы, 2-12
   символов, без пробелов),
   фракцию, расу, пол, класс, параметры внешности.
   Для каждого параметра внешности:
     "По умолчанию" — не трогать;
     число N — выбрать вариант с номером N;
     "Случайно" — случайный вариант (1-8).
5. Нажми "Старт" и не трогай мышь/клавиатуру.

ТЕСТОВЫЙ РЕЖИМ
- Поставь флажок "Тестовый режим" и нажми "Старт": программа пройдет весь
  сценарий (раса, класс, пол, внешность, имя), но НЕ будет нажимать
  "Завершить" — вместо этого подаст звуковой сигнал и остановится.
  Проверь глазами, что персонаж настроен верно, затем сними флажок и
  запусти обычный режим.

ТЕСТ РЕЛОГА
- Нажми кнопку "Тест релога (30 сек × 3)": программа настроит персонажа,
  затем выполнит 3 релога с интервалом 30 секунд и после каждого повторит
  настройку. Перед каждым релогом сообщение и звуковой сигнал укажут, что
  персонаж готов. "Завершить" и опасный Enter не нажимаются: создание
  персонажа в тесте заблокировано. Остановка после успеха отключена.
  Для досрочной остановки нажми "Стоп".

УПРОЩЁННЫЙ РЕЖИМ
- Поставь флажок "Упрощённый режим": программа НЕ трогает расу, класс,
  внешность и имя (ты выбираешь всё сам в клиенте). Она только циклически
  нажимает "Завершить", а если появляется окно ошибки — "ОК", и ждёт
  следующей попытки. Релог в этом режиме отключён.

КАК ЭТО РАБОТАЕТ
- При старте и после каждого релога программа заново выбирает расу, класс,
  пол, настраивает внешность и вводит имя.
- Далее цикл: нажимает "Завершить" и ждет. Если персонаж не создан
  (ошибка сети) — ждет случайный интервал из диапазона и повторяет.
- Если сервер отвечает, что фракция временно недоступна, программа сама
  нажмет "ОК" в информационном окне и повторит попытку.
- Если включен релог, раз в указанный диапазон минут программа жмет Esc
  (выход к экрану "Переподключение"), затем Enter и повторяет весь цикл.
- Если отмечено "Есть персонажи на других серверах", программа выходит
  кнопками "Назад": кастомизация → выбор расы (1 секунда) → список PvP
  (5 секунд) → переподключение (10 секунд). После Enter программа ждет
  20 секунд, нажимает "Свод правил", через 5 секунд выбирает PvP,
  нажимает "Выбрать" и ждет 30 секунд. Если открылся список персонажей,
  нажимает "Создание персонажа", ждет 2 секунды и продолжает настройку
  после появления экрана выбора расы и класса.
- При появлении списка персонажей программа считает создание успешным
  и останавливается (если не снят флажок "Остановиться после успеха").

ЭКСТРЕННАЯ ОСТАНОВКА
- Кинь курсор мыши в самый левый верхний угол экрана, либо
  нажми кнопку "Стоп" в программе.

ЕСЛИ ЧТО-ТО ПОШЛО НЕ ТАК
- Все действия пишутся в лог (окно справа и файл wow_char_auto_log.txt).
- Если включены отладочные скриншоты, в папке debug_shots сохраняются
  снимки экрана на каждой проверке состояния — пришли их, если
  программа ошибочно определяет экран.
- Если случайно откроется Главное меню (Esc) — программа сама нажмет
  "Закрыть" и продолжит работу.
"""


# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------
def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def load_settings():
    path = os.path.join(app_dir(), SETTINGS_FILE)
    cfg = dict(DEFAULTS)
    try:
        with open(path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        cfg.update({k: v for k, v in saved.items() if k in cfg})
    except Exception:
        pass
    return cfg


def save_settings(cfg):
    path = os.path.join(app_dir(), SETTINGS_FILE)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Не удалось сохранить настройки:", e)


# ---------------------------------------------------------------------------
# Бот
# ---------------------------------------------------------------------------
# Координаты как доли (fx, fy) от размера клиентской области окна игры.
POS = {
    "gender_male": (0.4825, 0.0385),
    "gender_female": (0.5175, 0.0385),
    "race_x": {"Альянс": 0.0425, "Орда": 0.1300},
    "race_y": [0.138, 0.218, 0.300, 0.380, 0.460],
    "class_y": 0.924,
    "class_icon_y": 0.899,   # сама иконка класса (подпись ниже)
    "class_x": [0.320, 0.360, 0.405, 0.4475, 0.490,
                0.5325, 0.575, 0.6175, 0.660],
    "next": (0.920, 0.932),
    "back": (0.083, 0.932),
    "charlist_back": (0.055, 0.969),
    "finish": (0.9175, 0.932),
    "name_first": (0.415, 0.0435),
    "name_last": (0.579, 0.0435),
    "name_status": (0.672, 0.036),
    "arrow_right_x": 0.9746,
    "arrow_left_x": 0.8602,
    "feature_step_y": 0.0716,
    "feature_ystart": 0.2833,   # у нежити 0.2208 (см. RACES)
    "reconnect": (0.5, 0.491),
    "charlist_rules": (0.566, 0.027),
    "new_character": (0.865, 0.900),
    "realm_pvp": (0.434, 0.520),
    "realm_choose": (0.932, 0.953),
    # контрольные точки для определения состояния экрана
    "probe_gender": (0.4825, 0.0385),   # иконка пола — яркая на экране выбора расы
    "probe_reconnect": (0.5, 0.491),    # красная кнопка "Переподключение"
    "probe_right": (0.920, 0.932),      # "Далее"/"Завершить"/"Меню"
    "probe_newchar": (0.940, 0.905),    # "Новая запись" — есть только в списке персонажей
}


class Bot:
    def __init__(self, cfg, log, is_stopped):
        self.cfg = cfg
        self.log = log
        self.is_stopped = is_stopped
        self.win = None
        self.client = (0, 0, 0, 0)
        self.debug_dir = os.path.join(app_dir(), "debug_shots")
        if cfg.get("debug_shots"):
            os.makedirs(self.debug_dir, exist_ok=True)

    # --- низкий уровень ----------------------------------------------------
    def find_window(self):
        for w in pgw.getAllWindows():
            if "warcraft" in (w.title or "").lower():
                return w
        return None

    def abs(self, fx, fy):
        x0, y0, cw, ch = self.client
        return (x0 + fx * cw, y0 + fy * ch)

    def click(self, fx, fy, desc=""):
        if self.cfg.get("relog_test") and (fx, fy) == POS["finish"]:
            self.log("ТЕСТ РЕЛОГА: клик по «Завершить» заблокирован.")
            return False
        x, y = self.abs(fx, fy)
        x += random.uniform(-3, 3)
        y += random.uniform(-2, 2)
        pyautogui.click(int(x), int(y))
        if desc:
            self.log(f"Клик: {desc}")
        return True

    def press(self, key, desc=""):
        if self.cfg.get("relog_test") and key.lower() == "enter":
            state = self.classify("relog_test_enter_guard")
            if state not in {"reconnect", "select"}:
                self.log("ТЕСТ РЕЛОГА: Enter заблокирован — подтверждён только "
                         f"экран '{state}', а не переподключение или выбор расы.")
                return False
        pyautogui.press(key)
        if desc:
            self.log(f"Клавиша: {desc}")
        return True

    def sleep(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            if self.is_stopped():
                raise StopIteration
            time.sleep(0.1)

    def pixel(self, fx, fy):
        x, y = self.abs(fx, fy)
        x, y = int(x), int(y)
        try:
            im = ImageGrab.grab(bbox=(x, y, x + 1, y + 1), all_screens=True)
            return im.getpixel((0, 0))[:3]
        except Exception:
            return (0, 0, 0)

    # --- определение состояния экрана --------------------------------------
    @staticmethod
    def is_red(c):
        r, g, b = c
        return r > 100 and r > g + 40 and r > b + 40

    @staticmethod
    def is_grey_button(c):
        r, g, b = c
        return 40 < r < 160 and max(c) - min(c) < 35

    @staticmethod
    def is_bright(c):
        return sum(c) > 300

    def ok_dialog_click(self):
        """Если открыт информационный диалог с красной кнопкой 'ОК'
        (напр. 'фракция временно недоступна') — нажать ОК.
        Кнопка ищется в центральной области экрана по форме
        (широкая горизонтальная красная полоса). False если окна нет."""
        try:
            x0, y0, cw, ch = self.client
            im = ImageGrab.grab(bbox=(x0, y0, x0 + cw, y0 + ch),
                                all_screens=True)
        except Exception:
            return False
        W, H = im.size
        step = 5
        y_start, y_end = int(H * 0.2), int(H * 0.9)
        x_start, x_end = int(W * 0.1), int(W * 0.9)
        rows = {}
        for y in range(y_start, y_end, step):
            xs = [x for x in range(x_start, x_end, step)
                  if self.is_red(im.getpixel((x, y))[:3])]
            if not xs:
                continue
            # самый длинный почти непрерывный пробег красного в строке
            best_run = None
            cur = [xs[0], xs[0]]
            for x in xs[1:]:
                if x - cur[1] <= step * 3:
                    cur[1] = x
                else:
                    if best_run is None or cur[1] - cur[0] > best_run[1] - best_run[0]:
                        best_run = list(cur)
                    cur = [x, x]
            if best_run is None or cur[1] - cur[0] > best_run[1] - best_run[0]:
                best_run = cur
            if best_run[1] - best_run[0] >= 50:   # ширина кнопки >= ~50px
                rows[y] = best_run
        if not rows:
            return False
        # группируем соседние строки в полосу (высота кнопки)
        ys_sorted = sorted(rows)
        band, bands = [ys_sorted[0]], []
        for y in ys_sorted[1:]:
            if y - band[-1] <= step * 5:   # допуск на «дырявый» градиент кнопки
                band.append(y)
            else:
                bands.append(band)
                band = [y]
        bands.append(band)
        best = None
        for b in bands:                       # ищем кнопку
            h = b[-1] - b[0]
            if not (8 <= h <= 90):
                continue
            x0 = min(rows[y][0] for y in b)
            x1 = max(rows[y][1] for y in b)
            w = x1 - x0
            if w < 120 or w / max(h, 1) < 3:    # кнопка: широкая и низкая
                continue
            if best is None or w > best[0]:
                best = (w, (x0 + x1) / 2, (b[0] + b[-1]) / 2)
        if best:
            _, cx, cy = best
            # проверка фона: кнопка ОК лежит на тёмной бирюзовой панели
            # диалога; красная одежда модели — на яркой сцене
            w = best[0]
            pts = [
                (cx - w / 2 - 25, cy), (cx + w / 2 + 25, cy),
                (cx - w / 2 - 25, cy - 15), (cx + w / 2 + 25, cy + 15),
                (cx, cy - 35), (cx, cy + 35),
            ]
            dark = 0
            for px_, py_ in pts:
                c = im.getpixel((int(px_), int(py_)))[:3]
                if sum(c) < 190:
                    dark += 1
            if dark < 4:
                return False
            # над кнопкой ОК в диалоге всегда несколько строк ярко-жёлтого
            # текста; у красной одежды модели над «полосой» текста нет
            def yellow(c):
                return (c[0] > 180 and c[1] > 150 and c[2] < 130
                        and c[0] >= c[1] - 20)
            k = W / 1920.0   # масштаб окна поиска под разрешение
            n_yellow = 0
            for py_ in range(int(cy - 160 * k), int(cy - 20 * k), 3):
                for px_ in range(int(cx - 250 * k), int(cx + 250 * k), 3):
                    if yellow(im.getpixel((px_, py_))[:3]):
                        n_yellow += 1
            if n_yellow < 30:
                return False
            self.log("Информационное окно с 'ОК' (вероятно, фракция"
                     " недоступна) — нажимаю ОК.")
            pyautogui.click(int(self.client[0] + cx), int(self.client[1] + cy))
            time.sleep(1.0)
            return True
        return False

    def screenshot_debug(self, tag):
        if not self.cfg.get("debug_shots"):
            return
        try:
            x0, y0, cw, ch = self.client
            im = ImageGrab.grab(bbox=(x0, y0, x0 + cw, y0 + ch),
                                all_screens=True)
            name = time.strftime("%H-%M-%S") + f"_{tag}.png"
            im.save(os.path.join(self.debug_dir, name))
        except Exception:
            pass

    def classify(self, tag="check"):
        # если открыто Главное меню (Esc) — закрыть и классифицировать заново
        cols = [self.pixel(0.4434, fy) for fy in (0.3819, 0.4861, 0.5903)]
        if all(50 <= c[0] <= 130 and 30 <= c[1] <= 90 and 15 <= c[2] <= 60
               for c in cols):
            self.log("Открыто Главное меню (Esc) — закрываю.")
            self.click(0.5, 0.611, "Закрыть")
            time.sleep(1.2)
        # информационный диалог с кнопкой "ОК" (напр. "фракция недоступна")
        if self.ok_dialog_click():
            time.sleep(0.5)
        p_gender = self.pixel(*POS["probe_gender"])
        p_recon = self.pixel(*POS["probe_reconnect"])
        p_right = self.pixel(*POS["probe_right"])
        p_newchar = self.pixel(*POS["probe_newchar"])
        p_create = self.pixel(*POS["new_character"])
        dark_reconnect = (75 <= p_recon[0] <= 160
                          and p_recon[1] < 30 and p_recon[2] < 30)
        dark_create = (75 <= p_create[0] <= 160
                       and p_create[1] < 30 and p_create[2] < 30)
        recon = ((self.is_red(p_recon) or dark_reconnect)
                 and sum(p_right) < 60)
        charlist = (self.is_red(p_newchar)
                    and (self.is_red(p_create) or dark_create))
        if charlist:
            state = "charlist"
        elif recon:
            state = "reconnect"
        elif self.is_bright(p_gender):
            state = "select"
        elif self.is_red(p_right) or self.is_grey_button(p_right):
            state = "custom"
        else:
            state = "unknown"
        self.log(f"Экран: {state} (пиксели: пол={p_gender}, центр={p_recon},"
                 f" угол={p_right}, новая запись={p_newchar},"
                 f" создание={p_create})")
        self.screenshot_debug(f"{tag}_{state}")
        return state

    def wait_state(self, wanted, timeout, tag="wait"):
        end = time.time() + timeout
        while time.time() < end:
            if self.is_stopped():
                raise StopIteration
            state = self.classify(tag)
            if state in wanted:
                return state
            time.sleep(1.5)
        return None

    # --- сценарии -----------------------------------------------------------
    def activate_window(self):
        self.win = self.find_window()
        if not self.win:
            raise RuntimeError("Окно World of Warcraft не найдено. "
                               "Запусти игру и войди в аккаунт.")
        try:
            if self.win.isMinimized:
                self.win.restore()
            self.win.activate()
        except Exception:
            pass
        # клиентская область окна (без рамки/заголовка): все координаты
        # считаются от неё, иначе в оконном режиме всё съезжает
        class _P(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        _rc = ctypes.wintypes.RECT()
        _pt = _P()
        _u32 = ctypes.windll.user32
        _u32.GetClientRect(self.win._hWnd, ctypes.byref(_rc))
        _u32.ClientToScreen(self.win._hWnd, ctypes.byref(_pt))
        self.client = (_pt.x, _pt.y,
                       _rc.right - _rc.left, _rc.bottom - _rc.top)
        self.log(f"Окно найдено: {self.win.title} {self.win.width}x"
                 f"{self.win.height}, клиент {self.client[2]}x"
                 f"{self.client[3]} @({self.client[0]},{self.client[1]})")

    def ensure_select_screen(self):
        """Привести клиент к экрану выбора расы/класса (изображение 1)."""
        for _ in range(6):
            state = self.classify("ensure")
            if state == "select":
                return True
            if state == "custom":
                self.click(*POS["back"], "Назад (из кастомизации)")
                self.sleep(2.5)
            elif state == "reconnect":
                self.press("enter", "Enter (переподключение)")
                self.sleep(4)
            else:
                self.press("esc", "Esc")
                self.sleep(2.5)
        return self.wait_state({"select"}, 20, "ensure_final") == "select"

    def race_selected(self, faction, idx):
        """Выбрана ли раса? У выбранного портрета верхняя яркая рамка
        заметно шире (≥60 px), чем тонкая кромка невыбранных."""
        fx = POS["race_x"][faction]
        fy = POS["race_y"][idx]
        x0, y0, cw, ch = self.client
        k = cw / 2576.0
        for dyf in (-0.044, -0.042, -0.040, -0.038, -0.036):
            y = int(y0 + (fy + dyf) * ch)
            xa = int(x0 + (fx - 0.04) * cw)
            xb = int(x0 + (fx + 0.05) * cw)
            try:
                im = ImageGrab.grab(bbox=(xa, y, xb, y + 1), all_screens=True)
            except Exception:
                return False
            xs = [x for x in range(im.size[0])
                  if self._is_frame_gold(im.getpixel((x, 0))[:3])]
            run = best = 0
            prev = None
            for x in xs:
                if prev is not None and x - prev <= max(2, int(6 * k)):
                    run += x - prev
                else:
                    best = max(best, run)
                    run = 0
                prev = x
            best = max(best, run)
            if best >= 60 * k:
                return True
        return False

    @staticmethod
    def _is_frame_gold(c):
        r, g, b = c
        return r > 170 and g > 120 and b < 250 and r >= b and g >= b

    def name_availability(self):
        """True — зелёная галка, False — красный крест, None — не определено."""
        x, y = self.abs(*POS["name_status"])
        x, y = int(x), int(y)
        k = self.client[2] / 2560.0
        radius = max(8, int(22 * k))
        try:
            im = ImageGrab.grab(bbox=(x - radius, y - radius,
                                      x + radius + 1, y + radius + 1),
                                all_screens=True)
        except Exception:
            return None
        green = red = 0
        for pixel in im.getdata():
            r, g, b = pixel[:3]
            if g > 100 and g > r + 40 and g > b + 30:
                green += 1
            if r > 110 and r > g + 50 and r > b + 40:
                red += 1
        min_hits = max(3, int(8 * k * k))
        if green >= min_hits and green > red:
            return True
        if red >= min_hits and red > green:
            return False
        return None

    def wait_name_availability(self, timeout=8):
        end = time.time() + timeout
        while time.time() < end:
            available = self.name_availability()
            if available is True:
                self.log("Имя персонажа доступно (зелёная галка).")
                return True
            if available is False:
                self.log("Имя персонажа занято или недоступно (красный крест).")
                return False
            self.sleep(0.5)
        self.log(f"Не удалось определить доступность имени за {timeout} сек."
                 " Продолжаю без подтверждения.")
        return None

    def do_full_flow(self):
        """Полный сценарий: раса/класс/пол -> Далее -> внешность -> имя -> Завершить."""
        cfg = self.cfg
        if not self.ensure_select_screen():
            self.log("Не удалось дождаться экрана выбора расы/класса.")
            return False

        # пол
        self.click(*POS["gender_female" if cfg["gender"] == "Женский"
                        else "gender_male"], f"Пол: {cfg['gender']}")
        self.sleep(0.6)

        # раса: кликаем до появления яркой рамки (макс. 3 попытки;
        # если мешает окно о недоступности фракции — закрываем его)
        race_list = RACES[cfg["faction"]]
        idx = next((i for i, r in enumerate(race_list)
                    if r["label"] == cfg["race"]), 0)
        faction_dialog = False
        for attempt in range(3):
            self.click(POS["race_x"][cfg["faction"]], POS["race_y"][idx],
                       f"Раса: {cfg['race']} (попытка {attempt + 1})")
            self.sleep(1.6)
            if self.race_selected(cfg["faction"], idx):
                break
            if self.ok_dialog_click():
                faction_dialog = True
            self.sleep(0.8)
        else:
            if faction_dialog:
                self.log("Раса не выбралась после 3 попыток. Возможно, фракция"
                         f" '{cfg['faction']}' временно недоступна на этом мире.")
                return False
            self.log("Не удалось подтвердить выбор расы по рамке, но окна"
                     " недоступности фракции нет. Продолжаю к выбору класса.")
        self.sleep(1.2)  # догрузка модели/классов

        # класс + Далее, при неудаче — повторная попытка
        for attempt in range(2):
            cidx = CLASSES.index(cfg["class"]) if cfg["class"] in CLASSES else 0
            # иконка класса; дублирующий клик по подписи — безвреден
            self.click(POS["class_x"][cidx], POS["class_icon_y"],
                       f"Класс: {cfg['class']} (иконка)")
            self.sleep(0.5)
            self.click(POS["class_x"][cidx], POS["class_y"],
                       f"Класс: {cfg['class']} (подпись)")
            self.sleep(0.8)
            self.click(*POS["next"], "Далее")
            if attempt == 1:
                self.press("enter", "Enter (дублирует 'Далее')")
            if self.wait_state({"custom"}, 12, "after_next"):
                break
            self.log("Экран кастомизации не появился — повторяю.")
            self.click(POS["race_x"][cfg["faction"]], POS["race_y"][idx],
                       f"Раса: {cfg['race']} (повтор)")
            self.sleep(1.6)
        else:
            self.log("Экран кастомизации не появился после повторов.")
            return False

        # внешность
        features = race_list[idx]["features"][cfg["gender"]]
        ystart = race_list[idx].get("ystart", 0.2833)
        app = cfg.get("appearance", {})
        for i, fname in enumerate(features):
            val = app.get(fname, "0")
            if val == "Случайно":
                val = str(random.randint(1, 8))
            if val.isdigit() and int(val) > 0:
                fy = ystart + i * POS["feature_step_y"]
                target = int(val)
                for _ in range(12):
                    self.click(POS["arrow_left_x"], fy,
                               f"Внешность: {fname} — сброс к 1")
                    self.sleep(0.1)
                for _ in range(target - 1):
                    self.click(POS["arrow_right_x"], fy, f"Внешность: {fname} +1")
                    self.sleep(0.2)
        self.sleep(0.4)

        # имя (полная очистка + Unicode-ввод не зависит от раскладки)
        for pos, desc, text in (
                (POS["name_first"], "Поле: основное имя", cfg["firstname"]),
                (POS["name_last"], "Поле: второе имя", cfg["lastname"])):
            self.click(*pos, desc)
            self.sleep(0.6)
            pyautogui.press("end")
            pyautogui.press("backspace", presses=24, interval=0.03)
            self.sleep(0.3)
            type_text(text)
            self.sleep(0.4)
        if cfg.get("test_mode") and self.wait_name_availability() is False:
            return False
        return True

    def enter_pvp_after_relog(self):
        self.log("Вход после релога: выбор PvP-сервера.")
        self.sleep(20)
        state = self.classify("relog_charlist")
        if state != "charlist":
            self.log("После переподключения не открылся список персонажей. "
                     "Выбор PvP-сервера отменён.")
            return False
        self.click(*POS["charlist_rules"], "Свод правил")
        self.sleep(5)
        self.click(*POS["realm_pvp"], "Тип игрового мира: PvP")
        self.sleep(1)
        self.click(*POS["realm_choose"], "Выбрать PvP-сервер")
        self.sleep(30)
        state = self.wait_state({"select", "charlist"}, 10, "after_relog_pvp")
        if state == "charlist":
            self.log("На PvP-сервере уже есть персонажи — открываю создание "
                     "нового персонажа.")
            self.click(*POS["new_character"], "Создание персонажа")
            self.sleep(2)
            if self.wait_state({"select"}, 10, "after_new_character") != "select":
                self.log("После нажатия «Создание персонажа» экран выбора расы "
                         "и класса не появился.")
                return False
        elif state != "select":
            self.log("После выбора PvP-сервера экран создания персонажа "
                     "не определился, пробую продолжить.")
        return True

    def exit_to_reconnect(self):
        self.log("Выход к переподключению через список персонажей PvP.")
        state = self.classify("relog_exit_start")
        if state == "reconnect":
            return True
        if state == "custom":
            self.click(*POS["back"], "Назад (из кастомизации)")
            self.sleep(1)
            state = self.classify("relog_exit_select")
        if state == "select":
            self.click(*POS["back"], "Назад (из выбора расы и класса)")
            self.sleep(5)
            state = self.classify("relog_exit_charlist")
        if state != "charlist":
            self.log("Не открылся список персонажей PvP. "
                     "Выход к переподключению отменён.")
            return False
        self.click(*POS["charlist_back"], "Назад (из списка персонажей PvP)")
        self.sleep(10)
        if self.classify("relog_exit_reconnect") != "reconnect":
            self.log("Экран переподключения не появился.")
            return False
        return True

    def do_relog(self):
        self.log("=== Релог ===")
        if self.cfg.get("has_other_server_chars"):
            if not self.exit_to_reconnect():
                return False
        else:
            self.press("esc", "Esc (к экрану переподключения)")
            self.sleep(3)
            state = self.classify("relog")
            if state != "reconnect":
                self.press("esc", "Esc (повторно)")
                self.sleep(2)
                if self.classify("relog_reconnect_retry") != "reconnect":
                    self.log("Экран переподключения не подтверждён. "
                             "Enter не нажимается.")
                    return False
        if not self.press("enter", "Enter (переподключение)"):
            return False
        if self.cfg.get("has_other_server_chars"):
            if not self.enter_pvp_after_relog():
                return False
        elif not self.wait_state({"select", "custom"}, 60, "after_relog"):
            self.log("После переподключения экран не определился, "
                     "пробую продолжить.")
        return self.do_full_flow()

    def notify_relog_test_ready(self):
        self.log("ТЕСТ РЕЛОГА: персонаж настроен до кнопки «Завершить». "
                 "Создание не выполняется; продолжаю тест.")
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            self.log("(звуковой сигнал недоступен)")

    def run_relog_test(self):
        self.log("=== ТЕСТ РЕЛОГА: 3 релога с интервалом 30 секунд ===")
        self.log("'Завершить' не нажимается; остановка после успеха отключена.")
        flow_ok = self.do_full_flow()
        if flow_ok:
            self.notify_relog_test_ready()
        else:
            self.log("Начальная настройка персонажа не удалась. "
                     "Тест релога продолжится.")
        for number in range(1, 4):
            self.log(f"Ожидание 30 секунд перед релогом {number}/3.")
            self.sleep(30)
            self.log(f"=== Тестовый релог {number}/3 ===")
            if self.do_relog():
                self.notify_relog_test_ready()
            else:
                self.log(f"Настройка персонажа после релога {number}/3 "
                         "не удалась. Тест продолжится.")
        self.log("=== Тест релога завершён: выполнено 3 релога. ===")

    def attempt_create(self):
        state = self.classify("attempt")
        if state == "custom":
            if self.wait_name_availability() is False:
                return "name_unavailable"
            self.click(*POS["finish"], "Завершить")
        elif state == "select":
            self.click(*POS["next"], "Далее")
        else:
            self.press("enter", "Enter (повтор)")
        self.sleep(8)
        state = self.classify("after_attempt")
        return state

    def handle_unknown(self):
        """Неопознанный экран: возможно, окно ошибки. Enter, потом Esc."""
        self.log("Неопознанный экран — пробую Enter/Esc.")
        self.press("enter", "Enter (закрыть возможное окно)")
        self.sleep(2.5)
        state = self.classify("after_enter")
        if state == "unknown":
            self.press("esc", "Esc")
            self.sleep(2.5)
            state = self.classify("after_esc")
        return state

    # --- главный цикл -------------------------------------------------------
    def run_simple(self):
        """Упрощённый режим: только 'Завершить' + 'ОК'. Пользователь сам
        настроил персонажа; бот лишь повторяет попытки создания."""
        self.cfg["relog_enabled"] = False
        self.log("=== УПРОЩЁННЫЙ РЕЖИМ: цикл «Завершить» + «ОК» ===")
        if self.cfg.get("test_mode"):
            # холостой прогон: ничего не нажимаем, только проверяем экран
            state = self.classify("simple_test")
            name_available = (state == "custom"
                              and self.wait_name_availability() is not False)
            try:
                import winsound
                if state == "custom" and name_available:
                    for _ in range(3):
                        winsound.MessageBeep(winsound.MB_ICONASTERISK)
                        time.sleep(0.7)
                    self.log("Тест пройден: бот на месте экрана кастомизации"
                             " и нажал бы «Завершить». В обычном запуске здесь"
                             " начался бы цикл попыток.")
                else:
                    winsound.MessageBeep(winsound.MB_ICONHAND)
                    if state == "custom":
                        self.log("Тест НЕ ПРОЙДЕН: имя персонажа занято"
                                 " или недоступно.")
                    else:
                        self.log(f"Тест НЕ ПРОЙДЕН: ожидался экран кастомизации,"
                                 f" определён '{state}'. Открой создание"
                                 f" персонажа и повтори.")
            except Exception:
                self.log("(звуковой сигнал недоступен)")
            return
        attempt = 0
        while not self.is_stopped():
            attempt += 1
            state = self.classify(f"simple{attempt}")
            if state == "charlist":
                self.log("Персонаж создан! Открыт список персонажей.")
                if self.cfg["stop_on_success"]:
                    return
            elif state == "custom":
                if self.wait_name_availability() is False:
                    self.log("Создание остановлено: выберите другое имя"
                             " персонажа.")
                    return
                self.click(*POS["finish"], "Завершить")
            elif state == "select":
                self.click(*POS["next"], "Далее")
            elif state == "reconnect":
                self.press("enter", "Enter (переподключение)")
            else:
                self.press("enter", "Enter")
            self.sleep(random.uniform(self.cfg["attempt_min"],
                                      self.cfg["attempt_max"]))
            state = self.classify(f"simple_after{attempt}")
            if state == "charlist":
                self.log("Персонаж создан! Открыт список персонажей.")
                if self.cfg["stop_on_success"]:
                    return
            elif state == "reconnect":
                self.press("enter", "Enter (переподключение)")
                self.sleep(5)

    def run(self):
        try:
            self.activate_window()
            if self.cfg.get("relog_test"):
                self.run_relog_test()
                return
            if self.cfg.get("simple_mode"):
                self.run_simple()
                return
            self.log("=== Запуск. Полный сценарий создания персонажа ===")
            flow_ok = self.do_full_flow()
            if self.cfg.get("test_mode"):
                self.log("=== ТЕСТОВЫЙ РЕЖИМ: 'Завершить' не нажимается ===")
                try:
                    import winsound
                    if flow_ok:
                        for _ in range(3):
                            winsound.MessageBeep(winsound.MB_ICONASTERISK)
                            time.sleep(0.7)
                        self.log("Тестовый прогон завершён. Проверьте, что"
                                 " раса, класс, внешность и имя настроены"
                                 " верно, затем запустите обычный режим.")
                    else:
                        winsound.MessageBeep(winsound.MB_ICONHAND)
                        self.log("Тест НЕ ПРОЙДЕН: сценарий не удался."
                                 " Смотрите лог выше и отладочные скриншоты.")
                except Exception:
                    self.log("(звуковой сигнал недоступен)")
                return
            if not flow_ok:
                self.log("ВНИМАНИЕ: полный сценарий не удался. Попытки"
                         " продолжатся, но проверьте настройки и экран игры.")
            next_relog = (time.time() + random.uniform(self.cfg["relog_min"],
                                                       self.cfg["relog_max"]) * 60
                          if self.cfg["relog_enabled"] else float("inf"))
            attempt = 0
            while not self.is_stopped():
                attempt += 1
                if time.time() >= next_relog:
                    self.do_relog()
                    next_relog = (time.time() + random.uniform(
                        self.cfg["relog_min"], self.cfg["relog_max"]) * 60)
                self.log(f"=== Попытка #{attempt} ===")
                state = self.attempt_create()
                if state == "name_unavailable":
                    self.log("Создание остановлено: выберите другое имя"
                             " персонажа.")
                    return
                if state == "charlist":
                    self.log("Персонаж, судя по всему, создан! "
                             "Открыт список персонажей.")
                    if self.cfg["stop_on_success"]:
                        self.log("Остановка (успех).")
                        return
                elif state == "custom":
                    wait = random.uniform(self.cfg["attempt_min"],
                                          self.cfg["attempt_max"])
                    self.log(f"Персонаж не создан (экран кастомизации на месте). "
                             f"Повтор через {wait:.1f} сек.")
                    self.sleep(wait)
                elif state == "reconnect":
                    self.log("Соединение потеряно — делаю релог.")
                    self.do_relog()
                elif state == "select":
                    self.log("Вернулись на экран выбора — повторяю полный сценарий.")
                    self.do_full_flow()
                else:
                    state = self.handle_unknown()
                    if state == "charlist":
                        self.log("Персонаж, судя по всему, создан!")
                        if self.cfg["stop_on_success"]:
                            return
                    elif state == "unknown":
                        self.log("Экран всё еще неопознан — делаю релог.")
                        self.do_relog()
        except StopIteration:
            self.log("Остановлено пользователем.")
        except pyautogui.FailSafeException:
            self.log("АВАРИЙНАЯ ОСТАНОВКА: мышь в углу экрана (failsafe).")
        except Exception:
            self.log("Ошибка:\n" + traceback.format_exc())


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} — v{APP_VERSION}")
        self.geometry("980x640")
        self.minsize(900, 600)
        self.cfg = load_settings()
        self.bot_thread = None
        self.stop_flag = threading.Event()

        self._build()
        self._load_to_widgets()
        self._sync_race_class()
        self._sync_simple()
        self.after(100, self._disclaimer)

    def _disclaimer(self):
        top = tk.Toplevel(self)
        top.title("Внимание")
        top.resizable(False, False)
        top.transient(self)
        top.grab_set()
        ttk.Label(top, wraplength=420, justify="center", padding=10,
                  text="Использование кликеров может привести к бану."
                       " Алгоритм создания разработан для минимизации шансов"
                       " обнаружения. Все риски пользователь берёт на себя."
                       "\n\nВы уверены, что готовы использовать приложение?"
                  ).pack(fill="both", expand=True)
        f = ttk.Frame(top, padding=10)
        f.pack(fill="x")
        ttk.Button(f, text="Ну его на фиг",
                   command=self.destroy).pack(side="left", expand=True,
                                              fill="x", padx=(0, 5))
        ttk.Button(f, text="Газгаз",
                   command=top.destroy).pack(side="left", expand=True,
                                             fill="x", padx=(5, 0))
        # центрирование по главному окну
        top.update_idletasks()
        w, h = top.winfo_reqwidth(), top.winfo_reqheight()
        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - w) // 2
        y = self.winfo_y() + (self.winfo_height() - h) // 2
        top.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")
        top.protocol("WM_DELETE_WINDOW", self.destroy)

    # --- построение интерфейса ---------------------------------------------
    def _build(self):
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=0)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        left = ttk.Frame(root, padding=(0, 0, 10, 0))
        left.grid(row=0, column=0, sticky="ns")

        right = ttk.Frame(root)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        r = 0
        ttk.Label(left, text="Разрешение окна игры:").grid(row=r, column=0, sticky="w")
        self.cb_res = ttk.Combobox(left, values=RESOLUTIONS, state="readonly",
                                   width=18)
        self.cb_res.grid(row=r, column=1, sticky="w", pady=2)
        r += 1

        ttk.Label(left, text="Интервал попыток (сек), от/до:").grid(row=r, column=0, sticky="w")
        f = ttk.Frame(left)
        f.grid(row=r, column=1, sticky="w")
        self.sp_amim = ttk.Spinbox(f, from_=5, to=300, width=6)
        self.sp_amax = ttk.Spinbox(f, from_=5, to=300, width=6)
        self.sp_amim.pack(side="left")
        self.sp_amax.pack(side="left", padx=(4, 0))
        r += 1

        ttk.Separator(left).grid(row=r, column=0, columnspan=2, sticky="ew", pady=6)
        r += 1

        self.var_simple = tk.BooleanVar()
        ttk.Checkbutton(left, text="Упрощённый режим (только «Завершить»/«ОК»,"
                                   " без настройки персонажа)",
                        variable=self.var_simple,
                        command=self._sync_simple).grid(row=r, column=0,
                                                        columnspan=2, sticky="w")
        r += 1

        ttk.Separator(left).grid(row=r, column=0, columnspan=2, sticky="ew", pady=6)
        r += 1

        # --- поля настройки персонажа (прячутся в упрощённом режиме) ---
        cf = ttk.Frame(left)
        cf.grid(row=r, column=0, columnspan=2, sticky="ew")
        self.custom_frame = cf
        cr = 0

        ttk.Label(cf, text="Основное имя:").grid(row=cr, column=0, sticky="w")
        self.en_first = ttk.Entry(cf, width=20)
        self.en_first.grid(row=cr, column=1, sticky="w", pady=2)
        cr += 1
        ttk.Label(cf, text="Второе имя:").grid(row=cr, column=0, sticky="w")
        self.en_last = ttk.Entry(cf, width=20)
        self.en_last.grid(row=cr, column=1, sticky="w", pady=2)
        cr += 1
        ttk.Label(cf, text="(рус/латиница, 2-12 символов, без пробелов)",
                  foreground="#666").grid(row=cr, column=0, columnspan=2, sticky="w")
        cr += 1

        ttk.Separator(cf).grid(row=cr, column=0, columnspan=2, sticky="ew", pady=6)
        cr += 1

        ttk.Label(cf, text="Фракция:").grid(row=cr, column=0, sticky="w")
        self.cb_faction = ttk.Combobox(cf, values=list(RACES.keys()),
                                       state="readonly", width=18)
        self.cb_faction.grid(row=cr, column=1, sticky="w", pady=2)
        self.cb_faction.bind("<<ComboboxSelected>>", self._sync_race_class)
        cr += 1
        ttk.Label(cf, text="Раса:").grid(row=cr, column=0, sticky="w")
        self.cb_race = ttk.Combobox(cf, state="readonly", width=18)
        self.cb_race.grid(row=cr, column=1, sticky="w", pady=2)
        self.cb_race.bind("<<ComboboxSelected>>", self._sync_race_class)
        cr += 1
        ttk.Label(cf, text="Пол:").grid(row=cr, column=0, sticky="w")
        self.cb_gender = ttk.Combobox(cf, values=["Мужской", "Женский"],
                                      state="readonly", width=18)
        self.cb_gender.grid(row=cr, column=1, sticky="w", pady=2)
        self.cb_gender.bind("<<ComboboxSelected>>", self._sync_race_class)
        cr += 1
        ttk.Label(cf, text="Класс:").grid(row=cr, column=0, sticky="w")
        self.cb_class = ttk.Combobox(cf, state="readonly", width=18)
        self.cb_class.grid(row=cr, column=1, sticky="w", pady=2)
        cr += 1

        ttk.Separator(cf).grid(row=cr, column=0, columnspan=2, sticky="ew", pady=6)
        cr += 1

        appf = ttk.LabelFrame(cf, text="Внешность (число = номер варианта)")
        appf.grid(row=cr, column=0, columnspan=2, sticky="ew", pady=4)
        self.app_widgets = {}  # feature -> Combobox
        self.app_frame = appf
        cr += 1
        r += 1

        ttk.Separator(left).grid(row=r, column=0, columnspan=2, sticky="ew", pady=6)
        r += 1

        self.var_relog = tk.BooleanVar()
        self.cb_relog = ttk.Checkbutton(
            left, text="Периодический релог, каждые (мин) от/до:",
            variable=self.var_relog)
        self.cb_relog.grid(row=r, column=0, sticky="w")
        self.relog_intervals = ttk.Frame(left)
        self.relog_intervals.grid(row=r, column=1, sticky="w")
        self.sp_rmin = ttk.Spinbox(self.relog_intervals, from_=1, to=180, width=6)
        self.sp_rmax = ttk.Spinbox(self.relog_intervals, from_=1, to=180, width=6)
        self.sp_rmin.pack(side="left")
        self.sp_rmax.pack(side="left", padx=(4, 0))
        r += 1

        self.var_other_servers = tk.BooleanVar()
        self.cb_other_servers = ttk.Checkbutton(
            left, text="Есть персонажи на других серверах",
            variable=self.var_other_servers)
        self.cb_other_servers.grid(row=r, column=0, columnspan=2, sticky="w")
        r += 1

        self.var_stop_success = tk.BooleanVar()
        ttk.Checkbutton(left, text="Остановиться после успешного создания",
                        variable=self.var_stop_success).grid(row=r, column=0,
                                                             columnspan=2, sticky="w")
        r += 1
        self.var_test = tk.BooleanVar()
        ttk.Checkbutton(left, text="Тестовый режим (1 прогон: звук вместо"
                                   " «Завершить»)",
                        variable=self.var_test).grid(row=r, column=0,
                                                     columnspan=2, sticky="w")
        r += 1
        self.var_debug = tk.BooleanVar()
        ttk.Checkbutton(left, text="Отладочные скриншоты (debug_shots)",
                        variable=self.var_debug).grid(row=r, column=0,
                                                      columnspan=2, sticky="w")
        r += 1

        btns = ttk.Frame(left)
        btns.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self.btn_start = ttk.Button(btns, text="Старт", command=self.start)
        self.btn_start.pack(side="left", expand=True, fill="x", padx=(0, 4))
        self.btn_stop = ttk.Button(btns, text="Стоп", command=self.stop,
                                   state="disabled")
        self.btn_stop.pack(side="left", expand=True, fill="x", padx=(0, 4))
        self.btn_help = ttk.Button(btns, text="Инструкция",
                                   command=self.show_help)
        self.btn_help.pack(side="left", expand=True, fill="x")
        r += 1

        self.btn_relog_test = ttk.Button(
            left, text="Тест релога (30 сек × 3)",
            command=self.start_relog_test)
        self.btn_relog_test.grid(row=r, column=0, columnspan=2,
                                 sticky="ew", pady=(6, 0))

        self.log_text = scrolledtext.ScrolledText(right, state="disabled",
                                                  wrap="word")
        self.log_text.grid(row=0, column=0, sticky="nsew")

    def _sync_simple(self):
        """В упрощённом режиме настройки персонажа и релог отключены."""
        simple = self.var_simple.get()
        if simple:
            self.custom_frame.grid_remove()
            self.var_relog.set(False)
        else:
            self.custom_frame.grid()
        self.cb_relog.configure(state="disabled" if simple else "normal")
        for widget in (self.cb_relog, self.relog_intervals,
                       self.cb_other_servers):
            if simple:
                widget.grid_remove()
            else:
                widget.grid()

    def _appearance_values(self):
        return ["По умолчанию"] + [str(i) for i in range(1, 13)] + ["Случайно"]

    def _sync_race_class(self, _evt=None):
        faction = self.cb_faction.get() or "Орда"
        races = RACES[faction]
        self.cb_race["values"] = [r["label"] for r in races]
        if self.cb_race.get() not in self.cb_race["values"]:
            self.cb_race.current(0)
        race = next(r for r in races if r["label"] == self.cb_race.get())
        self.cb_class["values"] = race["classes"]
        if self.cb_class.get() not in race["classes"]:
            self.cb_class.current(0)
        self._rebuild_appearance(race)

    def _rebuild_appearance(self, race):
        for w in self.app_frame.winfo_children():
            w.destroy()
        self.app_widgets = {}
        gender = self.cb_gender.get() or "Мужской"
        saved = self.cfg.get("appearance", {})
        for i, fname in enumerate(race["features"][gender]):
            ttk.Label(self.app_frame, text=fname + ":").grid(
                row=i, column=0, sticky="w", padx=(6, 2), pady=1)
            cb = ttk.Combobox(self.app_frame, values=self._appearance_values(),
                              state="readonly", width=14)
            val = saved.get(fname, "По умолчанию")
            cb.set(val if val in self._appearance_values() else "По умолчанию")
            cb.grid(row=i, column=1, sticky="w", pady=1)
            self.app_widgets[fname] = cb

    # --- настройки <-> виджеты ----------------------------------------------
    def _load_to_widgets(self):
        c = self.cfg
        self.cb_res.set(c["resolution"])
        self.sp_amim.delete(0, "end"); self.sp_amim.insert(0, str(c["attempt_min"]))
        self.sp_amax.delete(0, "end"); self.sp_amax.insert(0, str(c["attempt_max"]))
        self.en_first.insert(0, c["firstname"])
        self.en_last.insert(0, c["lastname"])
        self.cb_faction.set(c["faction"])
        races = RACES.get(c["faction"], RACES["Орда"])
        self.cb_race["values"] = [r["label"] for r in races]
        race_labels = [r["label"] for r in races]
        self.cb_race.set(c["race"] if c["race"] in race_labels else race_labels[0])
        self.cb_gender.set(c["gender"] if c["gender"] in ("Мужской", "Женский")
                           else "Мужской")
        race = next(r for r in races if r["label"] == self.cb_race.get())
        self.cb_class["values"] = race["classes"]
        self.cb_class.set(c["class"] if c["class"] in race["classes"]
                          else race["classes"][0])
        self._rebuild_appearance(race)
        self.var_relog.set(c["relog_enabled"])
        self.sp_rmin.delete(0, "end"); self.sp_rmin.insert(0, str(c["relog_min"]))
        self.sp_rmax.delete(0, "end"); self.sp_rmax.insert(0, str(c["relog_max"]))
        self.var_other_servers.set(c["has_other_server_chars"])
        self.var_stop_success.set(c["stop_on_success"])
        self.var_debug.set(c["debug_shots"])
        self.var_test.set(c.get("test_mode", False))
        self.var_simple.set(c.get("simple_mode", False))

    def _collect_cfg(self):
        c = dict(self.cfg)
        c["resolution"] = self.cb_res.get()
        c["attempt_min"] = int(self.sp_amim.get())
        c["attempt_max"] = int(self.sp_amax.get())
        c["firstname"] = self.en_first.get().strip()
        c["lastname"] = self.en_last.get().strip()
        c["faction"] = self.cb_faction.get()
        c["race"] = self.cb_race.get()
        c["gender"] = self.cb_gender.get()
        c["class"] = self.cb_class.get()
        c["appearance"] = {k: w.get() for k, w in self.app_widgets.items()}
        c["relog_enabled"] = self.var_relog.get() and not self.var_simple.get()
        c["relog_min"] = int(self.sp_rmin.get())
        c["relog_max"] = int(self.sp_rmax.get())
        c["has_other_server_chars"] = self.var_other_servers.get()
        c["stop_on_success"] = self.var_stop_success.get()
        c["debug_shots"] = self.var_debug.get()
        c["test_mode"] = self.var_test.get()
        c["simple_mode"] = self.var_simple.get()
        return c

    # --- лог ------------------------------------------------------------------
    def log(self, msg):
        line = time.strftime("[%H:%M:%S] ") + msg

        def _append():
            self.log_text.configure(state="normal")
            self.log_text.insert("end", line + "\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")

        self.after(0, _append)
        try:
            with open(os.path.join(app_dir(), LOG_FILE), "a",
                      encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    # --- управление ------------------------------------------------------------
    def validate(self, c):
        if c.get("simple_mode"):
            if c["attempt_min"] > c["attempt_max"]:
                messagebox.showerror("Проверка", "Интервал попыток:"
                                     " 'от' больше 'до'.")
                return False
            return True   # имя/раса/класс/внешность в упрощённом режиме
                          # не используются — пользователь всё выбрал сам
        for key, label in (("firstname", "Основное имя"),
                           ("lastname", "Второе имя")):
            if not NAME_RE.match(c[key]):
                messagebox.showerror("Проверка имени",
                                     f"{label}: русские или латинские буквы,"
                                     f" 2-12 символов, без пробелов.")
                return False
        if c["attempt_min"] > c["attempt_max"]:
            messagebox.showerror("Проверка", "Интервал попыток: 'от' больше 'до'.")
            return False
        if c["relog_enabled"] and c["relog_min"] > c["relog_max"]:
            messagebox.showerror("Проверка", "Интервал релога: 'от' больше 'до'.")
            return False
        return True

    def start(self):
        c = self._collect_cfg()
        if not self.validate(c):
            return
        self.cfg = c
        save_settings(c)
        self._launch(c)

    def start_relog_test(self):
        c = self._collect_cfg()
        c["simple_mode"] = False
        if not self.validate(c):
            return
        self.cfg = c
        save_settings(c)
        test_cfg = dict(c)
        test_cfg.update(relog_test=True, test_mode=True,
                        relog_enabled=True, stop_on_success=False)
        self._launch(test_cfg)

    def _launch(self, c):
        self.stop_flag.clear()
        self.btn_start.configure(state="disabled")
        self.btn_relog_test.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        bot = Bot(c, self.log, self.stop_flag.is_set)
        self.bot_thread = threading.Thread(target=self._run_bot, args=(bot,),
                                           daemon=True)
        self.bot_thread.start()

    def _run_bot(self, bot):
        try:
            bot.run()
        finally:
            self.after(0, self._on_bot_finished)

    def _on_bot_finished(self):
        self.btn_start.configure(state="normal")
        self.btn_relog_test.configure(state="normal")
        self.btn_stop.configure(state="disabled")

    def stop(self):
        self.log("Остановка...")
        self.stop_flag.set()

    def show_help(self):
        top = tk.Toplevel(self)
        top.title("Инструкция")
        top.geometry("640x560")
        txt = scrolledtext.ScrolledText(top, wrap="word")
        txt.pack(fill="both", expand=True, padx=8, pady=8)
        txt.insert("1.0", INSTRUCTION)
        txt.configure(state="disabled")
        ttk.Button(top, text="Закрыть", command=top.destroy).pack(pady=(0, 8))


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
