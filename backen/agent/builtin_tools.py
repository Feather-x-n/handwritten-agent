from datetime import datetime
from zoneinfo import ZoneInfo

from .tools import tool
_CITY_TZ = {
    "北京": "Asia/Shanghai",
    "上海": "Asia/Shanghai",
    "纽约": "America/New_York",
    "伦敦": "Europe/London",
}
@tool
def get_current_time(city:str = "北京")->str:
    """查询指定城市的当前日期和时间。用户问现在几点、今天几号、某地时间时使用。"""
    tz_name = _CITY_TZ.get(city)
    if tz_name is None:
        return f"错误：不支持的城市 {city}，可选 {list(_CITY_TZ.keys())}"
    now = datetime.now(ZoneInfo(tz_name))
    return now.strftime("%Y-%m-%d %H:%M:%S")
_WEATHER = {
    "北京": (22, "晴"),
    "上海": (25, "多云"),
    "纽约": (18, "小雨"),
    "伦敦": (14, "阴"),
}
 
@tool
def get_weather(city: str, unit: str = "celsius") -> str:
    """查询城市实时天气。用户问天气、气温、要不要带伞时使用。"""
    data = _WEATHER.get(city)
    if data is None:
        return f"错误：没有 {city} 的天气数据"
    temp, desc = data
    if unit == "fahrenheit":
        temp = round(temp * 9 / 5 + 32)
    return f"{city}：{desc}，{temp}°{'F' if unit == 'fahrenheit' else 'C'}"
    
