import os
def load_chunks(path: str) -> list:
    """
    遍历 docs 文件夹下所有 .md 文件
    每个文件按两个换行 \n\n 切分段落
    返回格式：[{"source": "文件名", "index": 段号, "text": "段落"}, ...]
    """
    result = []
    docs_dir = path
    #遍历文件夹下的所有.md文件
    for filename in sorted(os.listdir(docs_dir)):
        if not filename.endswith(".md"):
            continue
        file_path = os.path.join(docs_dir, filename)
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            #将内容以//n/n分割成段落
            chunks = content.split("\n\n")
            seg_index = 1
            for chunk in chunks:
                chunk = chunk.strip()
                if not chunk:
                    continue
                result.append(
                    {"source": filename, 
                     "index": seg_index, 
                     "text": chunk}
                     )
                seg_index += 1
    return result