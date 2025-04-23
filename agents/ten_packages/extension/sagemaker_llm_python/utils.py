from datetime import datetime
from .property import PUNCUTATIONS

def get_current_time():
    # Get the current time
    start_time = datetime.now()
    # Get the number of microseconds since the Unix epoch
    unix_microseconds = int(start_time.timestamp() * 1_000_000)
    return unix_microseconds


def parse_sentence(sentence, content):
    remain = ""
    found_punc = False

    for char in content:
        if not found_punc:
            sentence += char
        else:
            remain += char

        if not found_punc and char in PUNCUTATIONS:
            found_punc = True

    return sentence, remain, found_punc


def get_content_before_last_punctuation(text):
    # 从后向前遍历字符串
    for i in range(len(text) - 1, -1, -1):
        if text[i] in PUNCUTATIONS:
            i += 1
            while i < len(text) -1 and text[i] == ' ':
                i += 1

            return text[:i], True

    return text, False

def remove_tailing_punctuations(text):
    while text and text[-1] in PUNCUTATIONS:
        text = text[:-1]
    return text

def count_word(language, text):
    if language.split('-')[0] in ['zh', 'jp', 'cn', 'th', 'lo', 'km', 'my', 'ar', 'vi']:
        return len(text)
    else:
        return len(text.split(' '))