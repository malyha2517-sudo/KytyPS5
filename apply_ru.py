#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Русификация KytyPS5 for Xbox (src/uwp/src).

Заменяет английские строковые литералы интерфейса на русские прямо в исходниках,
ничего не добавляя в код. Работает на любой версии: строки, которых нет в словаре,
остаются английскими, а скрипт печатает список таких кандидатов.

    python apply_ru.py <путь к src/uwp/src> [--dry-run]
"""
import re, sys, glob, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ru_part1 import RU1
from ru_part2 import RU2
from ru_part3 import RU3
from ru_part4 import RU4
from ru_part5 import RU5

DICT = {}
for d in (RU1, RU2, RU3, RU4, RU5):
    DICT.update(d)

LIT = re.compile(r'L"((?:[^"\\]|\\.)*)"')
RAW = re.compile(r'LR"(\w*)\((.*?)\)\1"', re.S)
# контексты, где текст используется как ключ/идентификатор: переводить нельзя
# контексты всей строки, где переводить нельзя (лог, шрифты, URI, JSON-ключи, тосты)
SKIP_CTX = re.compile(
    r'x:Name|Segoe|FontFamily|Uri|kyty://|GetNamedString|GetNamedValue|JsonObject|\.at\(|\.contains\(|'
    r'\bLog\w*\(|LOG|OutputDebug|ToastGeneric|FileTypeFilter')
# литерал сразу после вызова поиска по имени/ресурсу = идентификатор, не текст
PRE_CTX = re.compile(r'(FindName|\bfind|\bpanel|Lookup|\bResource|\bresource|AppStyle|\bstyle|StartAnimation|'
                     r'box_value|\bInsert|\bTag|NumeralSystem|target\([^()]*,\s*[^(),]*,)\s*\(?\s*$')
# контексты сравнения: если текст встречается так хоть раз, он исключается везде
CMP_CTX = re.compile(r'(==|!=)\s*(std::wstring\(|winrt::hstring\()?L"|L"[^"]*"\s*\)?\s*(==|!=)|'
                     r'\.(find|rfind|starts_with|ends_with|compare)\(\s*L"')
XATTR = re.compile(r'\b(Text|Content|Header|PlaceholderText|Title|PrimaryButtonText|CloseButtonText)="([^"{][^"]*)"')
XTEXT = re.compile(r'>([^<>{}\n]*[A-Za-z]{2,}[^<>{}\n]*)<')

def merged_literals(s):
    """Соседние литералы ("a" "b") считаем одной строкой. Возвращает [(start, end, text)]."""
    raws = [(m.start(), m.end()) for m in RAW.finditer(s)]
    inraw = lambda p: any(a <= p < b for a, b in raws)
    ms = [m for m in LIT.finditer(s) if not inraw(m.start())]
    out, i = [], 0
    while i < len(ms):
        j, txt = i, ms[i].group(1)
        while j + 1 < len(ms) and re.fullmatch(r'\s*', s[ms[j].end():ms[j + 1].start()]):
            j += 1
            txt += ms[j].group(1)
        out.append((ms[i].start(), ms[j].end(), txt))
        i = j + 1
    return out

def line_of(s, pos):
    a = s.rfind('\n', 0, pos) + 1
    b = s.find('\n', pos)
    return s[a:b if b != -1 else len(s)]

def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    root, dry = sys.argv[1], '--dry-run' in sys.argv
    files = sorted(glob.glob(os.path.join(root, '*.cpp')) + glob.glob(os.path.join(root, '*.h')))
    texts = {f: open(f, encoding='utf-8').read() for f in files}

    # 1) тексты, участвующие в сравнениях, не трогаем нигде
    banned = set()
    for s in texts.values():
        for a, b, t in merged_literals(s):
            if CMP_CTX.search(line_of(s, a)):
                banned.add(t)

    done = collections.Counter(); skipped = collections.Counter(); missing = collections.Counter()
    for f, s in texts.items():
        # --- XAML-разметка ---
        def fix_raw(m):
            pre, body = m.group(1), m.group(2)
            def a(mm):
                v = mm.group(2)
                if v in DICT:
                    done[v] += 1
                    return '%s="%s"' % (mm.group(1), DICT[v])
                missing['XAML:' + v] += 1
                return mm.group(0)
            def t(mm):
                v = mm.group(1).strip()
                if v in DICT:
                    done[v] += 1
                    return mm.group(0).replace(v, DICT[v])
                missing['XAML:' + v] += 1
                return mm.group(0)
            body = XATTR.sub(a, body)
            body = XTEXT.sub(t, body)
            return 'LR"%s(%s)%s"' % (pre, body, pre)
        s = RAW.sub(fix_raw, s)

        # --- обычные литералы (с конца, чтобы не сбивать смещения) ---
        for a, b, t in reversed(merged_literals(s)):
            if t not in DICT:
                if re.search(r'[A-Za-z]{3,} [A-Za-z]{2,}', t) and not SKIP_CTX.search(line_of(s, a)):
                    missing[t] += 1
                continue
            if t in banned or SKIP_CTX.search(line_of(s, a)) or PRE_CTX.search(s[max(0, a - 60):a]):
                skipped[t] += 1
                continue
            s = s[:a] + 'L"' + DICT[t] + '"' + s[b:]
            done[t] += 1
        texts[f] = s

    if not dry:
        for f, s in texts.items():
            open(f, 'w', encoding='utf-8', newline='').write(s)
    print('заменено вхождений:', sum(done.values()), '| уникальных строк:', len(done))
    print('пропущено (ключи/сравнения):', sum(skipped.values()))
    unused = [k for k in DICT if k not in done and k not in skipped]
    print('в словаре, но не найдено в коде:', len(unused))
    print('\n--- не переведено (кандидаты) ---')
    for k, n in missing.most_common():
        print(' ', repr(k)[:110])
    print('\n--- словарь без совпадений ---')
    for k in unused[:80]:
        print(' ', repr(k)[:110])

main()
