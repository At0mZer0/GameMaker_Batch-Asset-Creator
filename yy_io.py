import json
import json5

BACKSLASH = chr(92)

# GameMaker writes .yy / .yyp files as JSON with trailing commas. json5 parses them
# but is pure python and slow when a room pulls in hundreds of object / sprite files.
# Stripping the trailing commas lets the C json module do the work, with json5 kept
# as a fallback for anything the stripper does not understand.

def stripTrailingCommas(text):
    # Walks the text once, blanking any comma that is followed only by whitespace
    # and a closing brace / bracket. String contents are skipped so a comma inside
    # a value like "Wood,}" is never touched.
    out = list(text)
    inString = False
    escaped = False
    pendingComma = -1

    for i, character in enumerate(text):
        if inString:
            if escaped:
                escaped = False
            elif character == BACKSLASH:
                escaped = True
            elif character == '"':
                inString = False
            continue

        if character == '"':
            inString = True
            pendingComma = -1
            continue

        if character in ' \t\r\n':
            continue

        if character == ',':
            pendingComma = i
            continue

        if character in '}]' and pendingComma >= 0:
            out[pendingComma] = ' '

        pendingComma = -1

    return ''.join(out)


def loadYY(filePath):
    # Loads any GameMaker .yy / .yyp file as a python dictionary
    with open(filePath, 'r', encoding='utf-8-sig') as file:
        text = file.read()
    try:
        return json.loads(stripTrailingCommas(text))
    except ValueError:
        return json5.loads(text)
