import warnings
warnings.filterwarnings("ignore", message=".*pin_memory", category=UserWarning)
import pymysql
from pymysql.cursors import DictCursor
import sys
from pathlib import Path
# 将项目根目录加入 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "external_lib"/"uie_pytorch"))
from configs import config
from agent.spell_check_agent import SpellCheckAgent
import easyocr
from tqdm import tqdm
from neo4j import GraphDatabase

from configs import config
from uie_predictor import UIEPredictor
from configs import config
from uie_predictor import UIEPredictor

# 1.从sku_image表中读取img_url,获取需要解析的图片url路径
"""
[{
    'sku_id': 36, 
    'img_url': '/data/images/36/1.jpg'
},
......
"""
def get_sku_img_erl():
    with pymysql.connect(**config.MYSQL_CONFIG) as connection:
        with connection.cursor(cursor=DictCursor) as cursor: # 获取游标
            cursor.execute("select sku_id, img_url from sku_image where img_url like '/data%'")
            result = cursor.fetchall()
    return result
# 2.通过easyocr进行图片解析
"""
{
'sku_id': [36, 36, 36, 36, 36], 
'image_text': ['购买客户尊享会员服务免', '', '']
}
"""
def get_sku_image_text(sku_image_urls):
    # 创建一个字典，用于存储图片的解析出来的文本内容
    sku_images_text = {"sku_id":[], "image_text":[]}
    reader = easyocr.Reader(['ch_sim','en'])

    # 遍历图片
    for item in tqdm(sku_image_urls, desc="图片解析中..."):
        try:
            result = reader.readtext(item["img_url"][1:],detail=0)
            image_text = "".join(result)
        except Exception as e:
            print(f"{item["img_url"]}图片解析失败，{e}")
            image_text = ""
        sku_images_text["sku_id"].append(item["sku_id"])
        sku_images_text["image_text"].append(image_text)
    return sku_images_text
# 3.对解析出来的图片内容进行拼写纠错
"""
{
'sku_id': [36, 36, 36, 36, 36], 
'image_text': ['纠错后的内容1', '纠错后的内容2', '']
}
"""
def correct_sku_image_text(sku_images_text):
    agent = SpellCheckAgent()
    for i, text in enumerate(sku_images_text["image_text"]):
        print(f"图片{i}原始内容：{text}")
        result = agent.correct(text)
        sku_images_text["image_text"][i] = result.corrected_text
        print(f"图片{i}纠错后内容：{result.corrected_text}")
    return sku_images_text
# 4.同时需要将sku_info表中sku_desc内容进行读取
"""
{'sku_id': [1, 2, 3, ...], 'sku_desc': ["xxx", "xxx"....]}
"""
def get_sku_desc():
    sku_desc = {"sku_id":[], "sku_desc":[]}
    with pymysql.connect(**config.MYSQL_CONFIG) as connection:
        with connection.cursor(cursor=DictCursor) as cursor: # 获取游标
            cursor.execute("select id sku_id,sku_desc from sku_info")
            result = cursor.fetchall()
    
    for item in result:
        sku_desc["sku_id"].append(item["sku_id"])
        sku_desc["sku_desc"].append(item["sku_desc"])

    return sku_desc
# 5.将图片的内容和sku_desc的内容进行实体抽取
"""
    {
        "sku_id": [1, 2, 3, ...],
        "sku_text": ["xxx", "xxx"....]
    }
    如何对sku_text中的内容进行实体抽取？使用之前介绍的UIE模型，抽取具体哪些特性呢？名称、类型、价格。。。。我们在什么地方定义过？


"""
def get_sku_entity(sku_text, schema):
    sku_entity = []
    sku_ids = sku_text["sku_id"] #所有商品的id
    ie = UIEPredictor(model="uie-base", schema=schema, task_path=config.CHECKPOINT_DIR/"uie"/"model_best")
    result = ie(sku_text["sku_text"])
    """
    result的数据格式：
        [{'商品': [{'end': 11,
          'probability': np.float32(0.9996733),
          'start': 0,
          'text': '小米12S Ultra'}],
            '颜色': [{'end': 63,
                    'probability': np.float32(0.999913),
                    'start': 60,
                    'text': '冷杉绿'}]
         },
            {'商品': [{'end': 22,
                    'probability': np.float32(0.9740904),
                    'start': 0,
                    'text': 'Apple/苹果 iPhone 16 Pro'}],
            '颜色': [{'end': 37,
                    'probability': np.float32(0.99906546),
                    'start': 35,
                    'text': '黑色'}]}]

        需要将上述格式转换成：
        [{"sku_id":sku_ids[0], "attr_name":"商品", "attr_value":result[0]["商品"][0]['text']},
        {"sku_id":sku_ids[0], "attr_name":"颜色", "attr_value":result[0]["颜色"][0]['text']},
        {"sku_id":sku_ids[1], "attr_name":"商品", "attr_value":result[0]["商品"][0]['text']}
       ...]
    """
for i, item in enumerate(result):
        """
        item的数据格式：
            {'商品': [{'end': 11,
          'probability': np.float32(0.9996733),
          'start': 0,
          'text': '小米12S Ultra'}],
            '颜色': [{'end': 63,
                    'probability': np.float32(0.999913),
                    'start': 60,
                    'text': '冷杉绿'}]
         }
        """
        for key, value in item.items(): # item.items()获取item字典中的键值对，key是属性名，value是属性值
            """
            '商品': [{'end': 11,
          'probability': np.float32(0.9996733),
          'start': 0,
          'text': '小米12S Ultra'}]
            """
            if key in schema:
                sku_entity.append({
                    "sku_id":sku_ids[i],
                    "attr_name":key,
                    "attr_value":value[0]['text']
                })
    return sku_entity
# 6.将抽取出来的实体内容写入neo4j中
"""
[
    {'sku_id': 36, 'attr_name': '显卡', 'attr_value': 'MX450'}, 
    {'sku_id': 1, 'attr_name': '版本', 'attr_value': '8GB+128GB'},
...
]
"""
def write_sku_entity_neo4j(sku_entity):
    with GraphDatabase.driver(
        uri=config.NEO4J_CONFIG["uri"], 
        auth=(config.NEO4J_CONFIG["user"], config.NEO4J_CONFIG["password"])) as driver:
        for entity in tqdm(sku_entity, desc="写入neo4j中..."):
            driver.execute_query(
                """
MATCH (sku:SKU{sku_id: $sku_id})
OPTIONAL MATCH (sku)-[:Have]->(attr_exist:Attr{attr_name: $attr_name})
WITH sku, attr_exist
WHERE attr_exist IS NULL
MERGE (attr:Attr {attr_name: $attr_name, attr_value: $attr_value})
MERGE (sku)-[:Have]->(attr)
""", 
database_="neo4j", parameters_=entity
            )
            if __name__ == '__main__':
    # 1.从sku_image表中读取img_url,获取需要解析的图片
    sku_image_urls = get_sku_img_url()
    #print(sku_image_urls)

    # 2. 通过easyocr进行图片解析,返回每个图片解析出来的文本内容
    sku_images_text = get_sku_image_text(sku_image_urls)
    #print(sku_images_text)
    
    # 3.对图片解析出来的内容进行拼写纠错
    sku_images_text = correct_sku_image_text(sku_images_text)
    #print(sku_images_text)

    # 4.同时需要将sku_info表中sku_desc内容进行读取
    sku_desc = get_sku_desc()
    
    # 5. 将图片的内容和sku_desc的内容进行合并，并进行实体抽取
    sku_text = {
        "sku_id":sku_images_text["sku_id"] + sku_desc["sku_id"],
        "sku_text":sku_images_text["image_text"] + sku_desc["sku_desc"]
    }

    schema = [
        "尺码",
        "观看距离",
        "分辨率",
        "屏幕尺寸",
        "电视类型",
        "版本",
        "颜色",
        "机身内存",
        "运行内存",
        "处理器或内存",
        "内存",
        "硬盘",
        "显卡",
        "处理器",
        "类别",
        "分类",
        "是否有机",
        "粮食调味",
        "面部护肤",
        "香水彩妆",
        "功效",
        "香调",
        "电池容量",
        "摄像头像素",
        "散热方式",
        "解锁方式",
	]
    sku_entity = get_sku_entity(sku_text, schema)
    #print(sku_entity)

    # 6.将抽取出来的实体内容写入neo4j中
    write_sku_entity_neo4j(sku_entity)
    print("写入完成")

