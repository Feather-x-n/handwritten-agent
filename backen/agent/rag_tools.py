from rag.search import search
from .tools import tool
#定义rag查询工具
@tool
def search_docs(query:str)->str:
    """
    检索公司制度、产品说明、运维文档时使用。返回结果包含来源文件名和段号，回答时必须标注来源。

    args:
        query (str): 查询关键词
    """
    reasult = search(query)
    if not reasult:
        return "没有找到相关文档"
    return "\n".join([f"文档：{item['source']}，段落索引：{item['index']}，相关度：{item['score']:.2f}\n内容：{item['text']}" for item in reasult])
    

    
