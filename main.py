#!/bin/python3

import argparse
import json
import os.path
import re

def log(msg):
    print("WARN:", msg)

def convert_filename_to_lang(filename: str) -> str:
    """
    Returns markdown langcode for code block, or "" if totally unknown.
    it might return non-supported langcode.
    """
    fn = filename.lower()
    ext_to_lang = {
        "py": "python",
        "js": "js",
    }
    ix = fn.rfind(".")
    if ix == -1:
        return ""
    ext = fn[ix+1:]
    return ext_to_lang.get(ext, ext)

def separate_head(s: str, symbol: str) -> tuple[int, str]:
    """
    Count c at the beginning of s, and return (count, rest).
    """
    rest = s.lstrip(symbol)
    return len(s) - len(rest), rest


def convert_linkish(content: str, entire_line: bool) -> str:
    """
    Convert link-ish things (anything that is [...])
    content is "..." part.
    Retrns markdown string.
    """
    # [* xxx] -> **xxx**
    # if sole text, treat as header
    # [** xxx]  -> ###### xxx (min header)
    # [*** xxx] -> ##### xxx
    # [**** xxx]  -> #### xxx
    # [***** xxx] -> ### xxx
    # [****** xxx] -> ## xxx
    # [******* xxx] (7) -> # xxx
    # [******** xxx] (8) -> # xxx (with warning about information loss)
    # [********** xxx] (10: biggest) -> # xxx (with warning about information loss)
    # if appears in the middle of the line, treat as bold (**xxx**)
    # for [** xxx] mid-text, emit bold with warning

    # link conversion
    # [https://gyazo.com/xxxx] -> ![](https://gyazo.com/xxxx.png)
    # [url] ->  url  (spaces before & after)
    # [xxxx url] -> [xxxx](url)
    # [xxxx] -> [[xxxx]]
    # [/proj/xxxx] -> [/proj/xxxx](https://scrapbox.com/proj/xxxx)
    # [xxxx.icon] -> (xxxx)

    if content.startswith("- "):
        return f"~~{content.removeprefix('- ')}~~"

    if content.startswith("*"):
        num_asterisk, rest = separate_head(content, "*")
        rest = rest.lstrip()
        if entire_line and num_asterisk > 1:
            return "#" * max(1, 8 - num_asterisk) + " " + rest
        else:
            if num_asterisk >= 2:
                log(f"WARN: link-ish object [{content}] is large-font bold, but converted to normal bold")
            return f"**{rest}**"
    
    # convert inter-project scrapbox link
    if content.startswith("/"):
        url = f"https://scrapbox.io{content}"
        return f"[{content}]({url})"

    # embed gyazo image as external image link
    if content.startswith("https://gyazo.com/"):
        url = content + ".png"
        return f"![]({url})"

    # embed youtube video
    if content.startswith("https://www.youtube.com/watch?v="):
        url = content
        return f"![]({url})"

    # check URL
    PAT_URL = r'^(.*\s+)(https?://\S+)$'
    m = re.match(PAT_URL, content)
    if m:
        desc = m.group(1).strip()
        url = m.group(2)
        
        if desc == "":
            return f" {url} "
        else:
            return f"[{desc}]({url})"
    
    # check icons
    if content.endswith(".icon"):
        username = content.removesuffix(".icon")
        return f"({username})"

    PAT_SYM = r'^[\x21-\x2F\x3A-\x40\x5B-\x60\x7B-\x7E]'
    if re.match(PAT_SYM, content):
        log(f"WARN: link-ish object [{content}] starts with special symbol, converted to `code`")
        return f"`{content}`"
    
    # in-project page-link
    return f"[[{content}]]"


def convert_line_content(lc: str) -> str:
    # escapes & literals
    # keep: `xxx` -> `xxx`

    res = []
    mode = None # None, "code" (`...`), "link" ([...])
    link_accum = ""

    for c in lc:
        if mode is None:
            if c == "`":
                mode = "code"
                res.append("`")
            elif c == "[":
                mode = "link"
                link_accum = ""
            else:
                res.append(c)
        elif mode == "code":
            if c == "`":
                mode = None
                res.append("`")
            else:
                res.append(c)
        elif mode == "link":
            if c == "`":
                mode = "code"
                res.append("`")
            elif c == "]":
                mode = None
                res.append(convert_linkish(link_accum, False))
            else:
                link_accum += c

    return "".join(res)


def convert_normal_line(line: str) -> str:
    # indent / list conversion
    #
    # "XXX" -> "XXX"
    # "\tXXX" -> "* XXX"
    # "\t\tXXX" -> "\t* XXX"
    # ...
    
    line_is_linkish = re.match(r'^\[[^\]]*\]$', line) is not None
    if line_is_linkish:
        return convert_linkish(line.strip("[]"), True)

    num_indents, content = separate_head(line, " \t")
    if num_indents > 0:
        return "\t" * (num_indents - 1) + "* " + convert_line_content(content)
    
    return convert_line_content(content)


def convert_page(page_json: any) -> str:
    # code block conversion
    # code:file.ext
    #  xxx1 (start with single space)
    #  xxx2
    # <empty>
    # ->
    # `file.ext`
    # ```<langname>
    # xxx1
    # xxx2
    # ```
    md_lines = []
    in_codeblock = False
    for line in page_json["lines"]:
        if in_codeblock:
            if line.startswith(" "):
                md_lines.append(line.removeprefix(" "))
            else:
                in_codeblock = False
                md_lines.append("```")
        else:
            if line.startswith("code:"):
                in_codeblock = True
                filename = line.removeprefix("code:")
                md_lines.append(f"`{filename}`")
                md_lines.append(f"```{convert_filename_to_lang(filename)}")
            else:
                md_lines.append(convert_normal_line(line))
    
    if in_codeblock:
        in_codeblock = False
        md_lines.append("```")

    md_lines.append("")
    return "\n".join(md_lines)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Covnert exported scrapbox JSON file to bunch of obsidian markdowns")
    parser.add_argument("src_json_path", help="Path to the source JSON file")
    parser.add_argument("dst_dir_path", help="Dst dir to put .md files")
    args = parser.parse_args()

    with open(args.src_json_path, "r") as f:
        data = json.load(f)

    FORBIDDEN_CHARS = "/\\<>:\"|?*"
    for page in data["pages"]:
        title = page["title"]
        print("Converting: ", title)
        for c in FORBIDDEN_CHARS:
            title = title.replace(c, "_")
        with open(os.path.join(args.dst_dir_path, title + ".md"), "w") as f:
            f.write(convert_page(page))
