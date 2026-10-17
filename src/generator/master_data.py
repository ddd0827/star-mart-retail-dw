"""连锁零售主数据生成：门店、商品、会员、品牌、品类、供应商、活动。"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

import numpy as np
import pandas as pd

REGIONS = [
    ("R01", "华东"), ("R02", "华北"), ("R03", "华南"),
    ("R04", "华中"), ("R05", "西南"), ("R06", "西北"),
]

CITIES = [
    # city_id, city_name, province, region_id, city_level, population_weight, districts
    ("CT01", "上海", "上海市", "R01", 1, 1.70, ["静安区", "浦东新区", "徐汇区"]),
    ("CT02", "杭州", "浙江省", "R01", 2, 1.10, ["西湖区", "拱墅区"]),
    ("CT03", "南京", "江苏省", "R01", 2, 1.00, ["鼓楼区", "江宁区", "建邺区"]),
    ("CT04", "北京", "北京市", "R02", 1, 1.70, ["朝阳区", "海淀区", "丰台区"]),
    ("CT05", "天津", "天津市", "R02", 2, 0.90, ["和平区"]),
    ("CT06", "广州", "广东省", "R03", 1, 1.40, ["天河区", "番禺区"]),
    ("CT07", "深圳", "广东省", "R03", 1, 1.50, ["南山区", "福田区"]),
    ("CT08", "武汉", "湖北省", "R04", 2, 1.10, ["武昌区", "洪山区"]),
    ("CT09", "长沙", "湖南省", "R04", 3, 0.80, ["岳麓区"]),
    ("CT10", "成都", "四川省", "R05", 1, 1.30, ["武侯区", "双流区", "成华区"]),
    ("CT11", "重庆", "重庆市", "R05", 2, 1.00, ["渝北区"]),
    ("CT12", "西安", "陕西省", "R06", 2, 0.90, ["雁塔区"]),
]
CITY_BY_ID = {c[0]: c for c in CITIES}
REGION_BY_ID = dict(REGIONS)

# (city_id, store_type, district)
STORE_LAYOUT = [
    ("CT01", "旗舰店", "静安区"),
    ("CT01", "标准店", "浦东新区"),
    ("CT01", "社区店", "徐汇区"),
    ("CT02", "标准店", "西湖区"),
    ("CT02", "社区店", "拱墅区"),
    ("CT03", "标准店", "鼓楼区"),
    ("CT03", "奥莱店", "江宁区"),
    ("CT03", "社区店", "建邺区"),
    ("CT04", "旗舰店", "朝阳区"),
    ("CT04", "标准店", "海淀区"),
    ("CT04", "社区店", "丰台区"),
    ("CT05", "标准店", "和平区"),
    ("CT06", "旗舰店", "天河区"),
    ("CT06", "社区店", "番禺区"),
    ("CT07", "旗舰店", "南山区"),
    ("CT07", "标准店", "福田区"),
    ("CT08", "标准店", "武昌区"),
    ("CT08", "社区店", "洪山区"),
    ("CT09", "标准店", "岳麓区"),
    ("CT10", "标准店", "武侯区"),
    ("CT10", "奥莱店", "双流区"),
    ("CT10", "社区店", "成华区"),
    ("CT11", "社区店", "渝北区"),
    ("CT12", "标准店", "雁塔区"),
]

STORE_TYPE_PARAMS = {
    "旗舰店": {"footfall": 1150, "conv": 0.110, "aov": 190, "level": "S"},
    "标准店": {"footfall": 620, "conv": 0.125, "aov": 172, "level": "A"},
    "社区店": {"footfall": 330, "conv": 0.155, "aov": 150, "level": "B"},
    "奥莱店": {"footfall": 450, "conv": 0.135, "aov": 160, "level": "B"},
    "线上履约仓": {"footfall": 0, "conv": 0.0, "aov": 0, "level": "W"},
}

CATEGORY_AFFINITY = {
    "旗舰店": {"食品饮料": 1.0, "生鲜果蔬": 1.0, "日化清洁": 1.0, "家居百货": 1.0, "服饰鞋包": 1.1, "数码家电": 1.1},
    "标准店": {"食品饮料": 1.1, "生鲜果蔬": 1.1, "日化清洁": 1.0, "家居百货": 0.95, "服饰鞋包": 0.9, "数码家电": 0.8},
    "社区店": {"食品饮料": 1.4, "生鲜果蔬": 1.5, "日化清洁": 1.2, "家居百货": 0.7, "服饰鞋包": 0.4, "数码家电": 0.3},
    "奥莱店": {"食品饮料": 0.8, "生鲜果蔬": 0.6, "日化清洁": 0.9, "家居百货": 1.1, "服饰鞋包": 1.5, "数码家电": 0.9},
    "线上履约仓": {"食品饮料": 1.0, "生鲜果蔬": 0.9, "日化清洁": 1.1, "家居百货": 1.0, "服饰鞋包": 1.0, "数码家电": 1.0},
}

ASSORT_PROB = {
    "旗舰店": {"食品饮料": 0.92, "生鲜果蔬": 0.92, "日化清洁": 0.90, "家居百货": 0.88, "服饰鞋包": 0.85, "数码家电": 0.80},
    "标准店": {"食品饮料": 0.82, "生鲜果蔬": 0.80, "日化清洁": 0.76, "家居百货": 0.62, "服饰鞋包": 0.50, "数码家电": 0.45},
    "社区店": {"食品饮料": 0.68, "生鲜果蔬": 0.72, "日化清洁": 0.58, "家居百货": 0.30, "服饰鞋包": 0.15, "数码家电": 0.15},
    "奥莱店": {"食品饮料": 0.50, "生鲜果蔬": 0.30, "日化清洁": 0.50, "家居百货": 0.55, "服饰鞋包": 0.72, "数码家电": 0.40},
    "线上履约仓": {"食品饮料": 0.95, "生鲜果蔬": 0.95, "日化清洁": 0.95, "家居百货": 0.95, "服饰鞋包": 0.95, "数码家电": 0.95},
}

TOP_CATEGORIES = {
    "食品饮料": ["休闲零食", "粮油调味", "乳品烘焙", "酒水饮料", "方便速食", "冲调饮品", "进口食品", "糖果巧克力"],
    "生鲜果蔬": ["新鲜水果", "时令蔬菜", "肉禽蛋品", "水产海鲜", "冷藏冷冻", "熟食凉菜", "豆制品"],
    "日化清洁": ["个人洗护", "家庭清洁", "口腔护理", "纸品湿巾", "美妆护肤", "母婴用品", "驱蚊防晒", "衣物护理"],
    "家居百货": ["厨房用品", "家纺床品", "收纳整理", "清洁工具", "家居饰品", "餐具水具", "卫浴用品", "五金工具"],
    "服饰鞋包": ["男装", "女装", "内衣家居", "运动户外", "鞋靴箱包", "配饰", "童装", "袜类"],
    "数码家电": ["小家电", "厨房电器", "手机配件", "智能设备", "影音娱乐", "个护电器", "办公文具"],
}

CATEGORY_PRODUCT_COUNT = {
    "食品饮料": 420, "生鲜果蔬": 330, "日化清洁": 250,
    "家居百货": 200, "服饰鞋包": 180, "数码家电": 120,
}

# 每个二级品类：商品词、规格、价格带、单位、保质期、是否生鲜
SUB_META: dict[str, dict] = {
    "休闲零食": dict(items=["每日坚果", "原味薯片", "苏打饼干", "手撕面包", "海苔脆片", "果冻布丁"],
                 specs=["袋装500g", "家庭装1kg", "分享装200g"], price=(6.9, 129.0), unit="袋", shelf=270, perishable=0),
    "粮油调味": dict(items=["东北大米", "压榨花生油", "生抽酱油", "香醋", "食用盐", "白砂糖"],
                 specs=["500ml", "1L", "5kg装"], price=(8.9, 159.0), unit="件", shelf=540, perishable=0),
    "乳品烘焙": dict(items=["鲜牛奶", "常温酸奶", "全麦吐司", "黄油可颂", "奶油蛋糕", "奶酪棒"],
                 specs=["250ml装", "盒装500g", "6枚装"], price=(3.5, 69.0), unit="盒", shelf=21, perishable=1),
    "酒水饮料": dict(items=["天然矿泉水", "无糖气泡水", "茉莉花茶", "精酿啤酒", "干红葡萄酒", "鲜榨橙汁"],
                 specs=["瓶装500ml", "箱装12瓶", "1.5L装"], price=(2.0, 299.0), unit="瓶", shelf=365, perishable=0),
    "方便速食": dict(items=["红烧牛肉面", "自热米饭", "速冻水饺", "即食燕麦", "螺蛳粉", "午餐肉"],
                 specs=["袋装", "盒装", "5连包"], price=(4.5, 59.0), unit="袋", shelf=270, perishable=0),
    "冲调饮品": dict(items=["挂耳咖啡", "即溶咖啡", "豆浆粉", "蜂蜜柚子茶", "高钙奶粉", "红茶包"],
                 specs=["罐装400g", "盒装20条", "袋装500g"], price=(9.9, 199.0), unit="盒", shelf=540, perishable=0),
    "进口食品": dict(items=["意大利面", "特级橄榄油", "进口饼干", "即食燕麦片", "坚果酱", "黑巧克力"],
                 specs=["500g", "1kg", "礼盒装"], price=(12.9, 199.0), unit="件", shelf=365, perishable=0),
    "糖果巧克力": dict(items=["黑巧克力", "牛奶糖", "水果软糖", "棒棒糖", "威化巧克力", "喜糖礼盒"],
                 specs=["袋装200g", "礼盒装", "分享装500g"], price=(5.9, 99.0), unit="盒", shelf=365, perishable=0),
    "新鲜水果": dict(items=["红富士苹果", "香蕉", "阳光玫瑰葡萄", "砂糖橘", "蓝莓", "麒麟西瓜"],
                 specs=["500g", "1kg", "礼盒装2.5kg"], price=(3.9, 89.0), unit="份", shelf=7, perishable=1),
    "时令蔬菜": dict(items=["有机菠菜", "西兰花", "土豆", "番茄", "黄瓜", "生菜"],
                 specs=["500g", "袋装300g", "1kg"], price=(2.5, 29.0), unit="份", shelf=5, perishable=1),
    "肉禽蛋品": dict(items=["黑猪五花肉", "鸡胸肉", "牛腩", "鲜鸡蛋", "鸭腿", "羊肉卷"],
                 specs=["500g", "1kg", "盒装"], price=(6.9, 129.0), unit="份", shelf=7, perishable=1),
    "水产海鲜": dict(items=["基围虾", "鲈鱼", "三文鱼", "扇贝", "带鱼", "花甲"],
                 specs=["500g", "1kg", "盒装"], price=(12.9, 199.0), unit="份", shelf=3, perishable=1),
    "冷藏冷冻": dict(items=["冷冻水饺", "冰淇淋", "速冻汤圆", "冷冻鸡翅", "冷鲜奶", "预制菜"],
                 specs=["袋装500g", "盒装", "家庭装1kg"], price=(5.9, 99.0), unit="份", shelf=180, perishable=1),
    "熟食凉菜": dict(items=["卤牛肉", "盐水鸭", "凉拌木耳", "手撕鸡", "酱鸭", "寿司拼盘"],
                 specs=["盒装250g", "盒装500g", "份"], price=(8.9, 59.0), unit="份", shelf=3, perishable=1),
    "豆制品": dict(items=["嫩豆腐", "老豆腐", "豆浆", "腐竹", "豆干", "油豆腐"],
                 specs=["袋装", "盒装", "散装500g"], price=(2.9, 19.0), unit="份", shelf=5, perishable=1),
    "个人洗护": dict(items=["氨基酸洗发水", "柔顺护发素", "香氛沐浴露", "温和洗面奶", "美白牙膏", "保湿身体乳"],
                 specs=["瓶装500ml", "家庭装1L", "旅行装100ml"], price=(9.9, 129.0), unit="瓶", shelf=1095, perishable=0),
    "家庭清洁": dict(items=["深层洁净洗衣液", "柠檬洗洁精", "衣物消毒液", "玻璃清洁剂", "地板清洁剂", "加厚垃圾袋"],
                 specs=["瓶装1L", "补充装2L", "组合装"], price=(6.9, 89.0), unit="瓶", shelf=1095, perishable=0),
    "口腔护理": dict(items=["防蛀牙膏", "软毛牙刷", "清新漱口水", "细滑牙线", "声波电动牙刷", "口腔喷雾"],
                 specs=["支装", "家庭装3支", "100ml"], price=(5.9, 99.0), unit="件", shelf=1095, perishable=0),
    "纸品湿巾": dict(items=["原生木浆抽纸", "无芯卷纸", "杀菌湿巾", "厨房纸巾", "手帕纸", "棉柔巾"],
                 specs=["3包装", "12卷装", "80抽"], price=(5.9, 69.0), unit="提", shelf=1095, perishable=0),
    "美妆护肤": dict(items=["补水面膜", "保湿面霜", "清透防晒霜", "丝绒口红", "修护精华液", "温和卸妆水"],
                 specs=["30ml", "50g", "礼盒装"], price=(19.9, 399.0), unit="件", shelf=1095, perishable=0),
    "母婴用品": dict(items=["超薄纸尿裤", "婴儿湿巾", "幼儿配方奶粉", "辅食米粉", "宽口奶瓶", "儿童牙膏"],
                 specs=["S码50片", "M码40片", "盒装"], price=(9.9, 299.0), unit="包", shelf=730, perishable=0),
    "驱蚊防晒": dict(items=["植物驱蚊液", "清爽防晒喷雾", "无烟蚊香", "电蚊香液", "花露水", "黑胶遮阳伞"],
                 specs=["瓶装100ml", "喷雾150ml", "家庭装"], price=(9.9, 119.0), unit="瓶", shelf=1095, perishable=0),
    "衣物护理": dict(items=["衣物柔顺剂", "洗衣凝珠", "衣物除菌液", "便携去渍笔", "羊毛烘干球", "防串色洗衣片"],
                 specs=["瓶装1L", "30颗装", "500ml"], price=(9.9, 79.0), unit="瓶", shelf=1095, perishable=0),
    "厨房用品": dict(items=["麦饭石不粘锅", "精铁炒锅", "厨房菜刀", "抗菌砧板", "保鲜盒", "多功能削皮器"],
                 specs=["单件装", "套装", "32cm"], price=(19.9, 499.0), unit="件", shelf=1825, perishable=0),
    "家纺床品": dict(items=["纯棉四件套", "护颈枕头", "夏凉空调被", "纯棉毛巾", "吸水浴巾", "床垫保护垫"],
                 specs=["1.5m床", "1.8m床", "四件套"], price=(39.0, 899.0), unit="套", shelf=1825, perishable=0),
    "收纳整理": dict(items=["透明收纳箱", "防滑衣架", "免钉挂钩", "抽屉分隔盒", "真空压缩袋", "多层置物架"],
                 specs=["中号", "大号", "3个装"], price=(9.9, 199.0), unit="件", shelf=1825, perishable=0),
    "清洁工具": dict(items=["扫把簸箕套装", "免手洗拖把", "超细纤维抹布", "清洁刷", "脚踏垃圾篓", "静电除尘掸"],
                 specs=["套装", "单件", "加长款"], price=(9.9, 199.0), unit="件", shelf=1825, perishable=0),
    "家居饰品": dict(items=["香薰蜡烛", "陶瓷花瓶", "原木相框", "抱枕", "装饰画", "棉麻桌布"],
                 specs=["单件", "礼盒装", "组合装"], price=(19.9, 299.0), unit="件", shelf=1825, perishable=0),
    "餐具水具": dict(items=["陶瓷饭碗", "骨瓷餐盘", "耐热玻璃杯", "真空保温杯", "合金筷子", "便当饭盒"],
                 specs=["单件", "6件套", "500ml"], price=(9.9, 299.0), unit="套", shelf=1825, perishable=0),
    "卫浴用品": dict(items=["太空铝毛巾架", "防水浴帘", "硅藻防滑垫", "漱口牙刷杯", "马桶刷套装", "浴室置物架"],
                 specs=["单件", "套装", "加厚款"], price=(9.9, 199.0), unit="件", shelf=1825, perishable=0),
    "五金工具": dict(items=["家用工具箱", "精密螺丝刀", "羊角锤", "钢卷尺", "安全插线板", "碱性电池"],
                 specs=["单件", "套装", "家用组套"], price=(9.9, 299.0), unit="件", shelf=3650, perishable=0),
    "男装": dict(items=["纯棉圆领T恤", "休闲衬衫", "直筒牛仔裤", "轻量夹克", "连帽卫衣", "修身西裤"],
                specs=["M码", "L码", "XL码"], price=(59.0, 699.0), unit="件", shelf=3650, perishable=0),
    "女装": dict(items=["法式连衣裙", "软糯针织衫", "高腰阔腿裤", "简约风衣", "A字半身裙", "雪纺衬衫"],
                specs=["S码", "M码", "L码"], price=(79.0, 899.0), unit="件", shelf=3650, perishable=0),
    "内衣家居": dict(items=["纯棉内裤", "无钢圈文胸", "睡衣套装", "家居服", "中筒袜", "保暖内衣"],
                 specs=["M码", "L码", "套装"], price=(19.9, 299.0), unit="件", shelf=1825, perishable=0),
    "运动户外": dict(items=["速干运动T恤", "缓震跑步鞋", "提臀瑜伽裤", "三合一冲锋衣", "轻量双肩包", "运动水壶"],
                 specs=["单件", "套装", "均码"], price=(49.0, 899.0), unit="件", shelf=3650, perishable=0),
    "鞋靴箱包": dict(items=["软底休闲鞋", "头层牛皮鞋", "经典帆布鞋", "通勤手提包", "真皮钱包", "万向轮行李箱"],
                 specs=["38码", "40码", "均码"], price=(59.0, 1299.0), unit="件", shelf=3650, perishable=0),
    "配饰": dict(items=["纯棉棒球帽", "羊绒围巾", "牛皮腰带", "偏光太阳镜", "石英手表", "淡水珍珠项链"],
                specs=["均码", "单件", "礼盒装"], price=(19.9, 499.0), unit="件", shelf=3650, perishable=0),
    "童装": dict(items=["儿童纯棉T恤", "公主连衣裙", "运动长裤", "防风外套", "学院风套装", "儿童运动鞋"],
                specs=["110码", "130码", "150码"], price=(39.0, 399.0), unit="件", shelf=1825, perishable=0),
    "袜类": dict(items=["精梳棉船袜", "中筒袜", "运动袜", "超薄丝袜", "加厚保暖袜", "儿童棉袜"],
                specs=["3双装", "5双装", "均码"], price=(9.9, 99.0), unit="双", shelf=1825, perishable=0),
    "小家电": dict(items=["便携电热水壶", "负离子电吹风", "空气循环扇", "卧室加湿器", "无油空气炸锅", "智能电饭煲"],
                 specs=["标准款", "升级款", "套装"], price=(59.0, 999.0), unit="台", shelf=1825, perishable=0),
    "厨房电器": dict(items=["高速破壁机", "智能微波炉", "超薄电磁炉", "多功能电烤箱", "胶囊咖啡机", "台式洗碗机"],
                 specs=["标准款", "智能款", "套装"], price=(129.0, 2999.0), unit="台", shelf=1825, perishable=0),
    "手机配件": dict(items=["20000mAh充电宝", "快充数据线", "氮化镓充电器", "防摔手机壳", "高清钢化膜", "入耳蓝牙耳机"],
                 specs=["标准款", "Pro款", "套装"], price=(19.9, 399.0), unit="件", shelf=1095, perishable=0),
    "智能设备": dict(items=["运动智能手环", "智能音箱", "智能插座", "扫拖机器人", "家用摄像头", "智能体脂秤"],
                 specs=["标准版", "Pro版", "套装"], price=(99.0, 3999.0), unit="台", shelf=1825, perishable=0),
    "影音娱乐": dict(items=["便携蓝牙音箱", "头戴式耳机", "无线游戏手柄", "智能投影仪", "4K电视盒子", "直播麦克风"],
                 specs=["标准款", "Pro款", "套装"], price=(49.0, 1999.0), unit="件", shelf=1825, perishable=0),
    "个护电器": dict(items=["声波电动牙刷", "全身水洗剃须刀", "便携冲牙器", "负离子卷发棒", "射频美容仪", "颈椎按摩仪"],
                 specs=["标准款", "升级款", "礼盒装"], price=(39.0, 1999.0), unit="台", shelf=1825, perishable=0),
    "办公文具": dict(items=["按动中性笔", "皮面笔记本", "资料文件夹", "省力订书机", "语音计算器", "护眼台灯"],
                 specs=["单件", "10支装", "套装"], price=(2.9, 299.0), unit="件", shelf=1825, perishable=0),
}

CATEGORY_MONTH_FACTOR = {
    "食品饮料": {4: 1.00, 5: 1.03, 6: 1.06, 7: 1.08, 8: 1.08, 9: 1.05, 10: 1.12},
    "生鲜果蔬": {4: 1.02, 5: 1.06, 6: 1.12, 7: 1.18, 8: 1.18, 9: 1.10, 10: 1.04},
    "日化清洁": {4: 1.00, 5: 0.98, 6: 1.02, 7: 1.05, 8: 1.05, 9: 1.00, 10: 1.02},
    "家居百货": {4: 0.96, 5: 1.00, 6: 1.02, 7: 1.00, 8: 1.02, 9: 1.06, 10: 1.10},
    "服饰鞋包": {4: 1.00, 5: 0.96, 6: 0.92, 7: 0.94, 8: 0.96, 9: 1.10, 10: 1.16},
    "数码家电": {4: 1.00, 5: 1.00, 6: 0.96, 7: 0.96, 8: 0.98, 9: 1.02, 10: 1.12},
}

TOP_CATEGORY_SEASON_PROFILE = {
    "食品饮料": "全年稳定，节庆走强",
    "生鲜果蔬": "夏季强，生鲜高频",
    "日化清洁": "全年稳定",
    "家居百货": "下半年走强",
    "服饰鞋包": "秋季换季走强",
    "数码家电": "大促与节庆走强",
}

STORE_CATEGORY_MAP = {
    "旗舰店": "全品类旗舰", "标准店": "标准社区商圈", "社区店": "社区高频",
    "奥莱店": "品牌折扣", "线上履约仓": "线上履约",
}


def month_category_factor(top_name: str, month: int) -> float:
    return CATEGORY_MONTH_FACTOR.get(top_name, {}).get(month, 1.0)


def _random_dates(rng: np.random.Generator, start: date, end: date, n: int) -> np.ndarray:
    if n <= 0:
        return np.array([], dtype="datetime64[D]")
    lo, hi = start.toordinal(), end.toordinal()
    ords = rng.integers(lo, hi + 1, size=n)
    return np.array([date.fromordinal(int(x)) for x in ords], dtype="datetime64[D]")


def build_master(config, rng: np.random.Generator) -> dict:
    n_members = int(config.scale["members"])
    n_skus = int(config.scale["skus"])

    # ---------------- 门店 ----------------
    store_rows = []
    manager_names = [
        "陈晓峰", "李静", "王磊", "赵敏", "刘洋", "周颖", "吴浩然", "徐婷",
        "孙建国", "马琳", "朱斌", "胡雪", "郭强", "何雨晴", "高远", "林可",
        "罗志强", "梁悦", "宋涛", "郑楠", "谢文博", "韩梅", "曹阳", "彭佳",
    ]
    for i, (city_id, store_type, district) in enumerate(STORE_LAYOUT, start=1):
        city = CITY_BY_ID[city_id]
        params = STORE_TYPE_PARAMS[store_type]
        base = params["footfall"] * (1 + rng.normal(0, 0.08))
        store_rows.append({
            "store_id": f"S{i:03d}",
            "store_name": f"星选生活·{city[1]}{district}{store_type}",
            "store_type": store_type,
            "city_id": city_id,
            "city_name": city[1],
            "province": city[2],
            "region_id": city[3],
            "region_name": REGION_BY_ID[city[3]],
            "address": f"{city[1]}{district}星选路{rng.integers(8, 288)}号",
            "open_date": str(date(2015 + int(rng.integers(0, 10)), int(rng.integers(1, 13)), int(rng.integers(1, 28)))),
            "area_sqm": int(rng.integers(180, 1501) if store_type == "旗舰店" else rng.integers(90, 700)),
            "manager_name": manager_names[i - 1],
            "is_offline": 1,
            "status": "营业",
            "update_time": "2026-10-16 23:00:00",
            "_base_footfall": float(base),
        })
    store_rows.append({
        "store_id": "W001",
        "store_name": "星选生活·上海线上履约仓",
        "store_type": "线上履约仓",
        "city_id": "CT01",
        "city_name": "上海",
        "province": "上海市",
        "region_id": "R01",
        "region_name": "华东",
        "address": "上海市浦东新区星选物流园1号",
        "open_date": "2021-06-18",
        "area_sqm": 8600,
        "manager_name": "顾承宇",
        "is_offline": 0,
        "status": "营业",
        "update_time": "2026-10-16 23:00:00",
        "_base_footfall": 0.0,
    })
    stores = pd.DataFrame(store_rows)

    # ---------------- 供应商 ----------------
    supplier_names = [
        "华东鲜食供应链有限公司", "京北粮油贸易有限公司", "江南烘焙食品有限公司", "岭南饮品供应链有限公司",
        "川渝调味品有限公司", "华北乳业商贸有限公司", "东海水产供应链有限公司", "湘江肉禽食品有限公司",
        "申城日化贸易有限公司", "鹏城清洁用品有限公司", "杭州母婴供应链有限公司", "姑苏纸品有限公司",
        "沪上美妆商贸有限公司", "津门家居用品有限公司", "天府家纺供应链有限公司", "羊城服饰有限公司",
        "鹏城鞋包贸易有限公司", "华中运动用品有限公司", "西部数码供应链有限公司", "长安小家电贸易有限公司",
        "华南影音供应链有限公司", "钱塘智能设备有限公司", "北方办公用品有限公司", "云贵生鲜供应链有限公司",
        "西北食品贸易有限公司",
    ]
    top_names = list(TOP_CATEGORIES.keys())
    suppliers = pd.DataFrame({
        "supplier_id": [f"SUP{i:02d}" for i in range(1, 26)],
        "supplier_name": supplier_names,
        "main_category": [top_names[i % len(top_names)] for i in range(25)],
        "province": [CITY_BY_ID[CITIES[i % len(CITIES)][0]][2] for i in range(25)],
        "contact_phone": [f"400-{rng.integers(100, 999)}-{rng.integers(1000, 9999)}" for _ in range(25)],
        "lead_time_days": rng.integers(2, 6, size=25),
        "status": "合作中",
        "update_time": "2026-10-16 20:00:00",
    })
    supplier_by_top = {top: suppliers[suppliers["main_category"] == top].reset_index(drop=True) for top in top_names}

    # ---------------- 品牌 ----------------
    brand_prefix = ["鲜", "禾", "初", "沐", "简", "悦", "本", "山", "海", "麦", "谷", "原", "优", "轻", "云", "星",
                    "拾", "知", "南", "北", "良", "小", "大", "白", "木", "青", "橙", "蓝", "晨", "暖"]
    brand_suffix = ["语", "味", "选", "集", "坊", "记", "生活", "良品", "食品", "家居", "优选", "工坊", "物语", "日记",
                    "研究所", "工房", "严选", "味道", "时代", "空间"]
    combos = [p + s for p in brand_prefix for s in brand_suffix]
    rng.shuffle(combos)
    selected = list(dict.fromkeys(combos))[:80]
    countries = ["中国", "中国", "中国", "中国", "日本", "美国", "法国", "德国", "澳大利亚"]
    brands = pd.DataFrame({
        "brand_id": [f"B{i:03d}" for i in range(1, len(selected) + 1)],
        "brand_name": selected,
        "brand_country": [countries[int(rng.integers(0, len(countries)))] for _ in selected],
        "status": "在售",
        "update_time": "2026-10-16 19:00:00",
    })
    brands["_top_category"] = [top_names[i % len(top_names)] for i in range(len(brands))]
    brand_by_top = {top: brands[brands["_top_category"] == top].reset_index(drop=True) for top in top_names}

    # ---------------- 品类 ----------------
    category_rows = []
    sub_to_top: dict[str, str] = {}
    for t_idx, (top_name, subs) in enumerate(TOP_CATEGORIES.items(), start=1):
        top_id = f"C{t_idx:02d}"
        category_rows.append({
            "category_id": top_id, "category_name": top_name, "parent_id": "",
            "level": 1, "category_path": top_name,
            "season_profile": TOP_CATEGORY_SEASON_PROFILE[top_name],
            "perishable": int(top_name == "生鲜果蔬"),
            "update_time": "2026-10-16 18:00:00",
        })
        for s_idx, sub_name in enumerate(subs, start=1):
            sub_id = f"{top_id}{s_idx:02d}"
            sub_to_top[sub_name] = top_name
            category_rows.append({
                "category_id": sub_id, "category_name": sub_name, "parent_id": top_id,
                "level": 2, "category_path": f"{top_name}/{sub_name}",
                "season_profile": TOP_CATEGORY_SEASON_PROFILE[top_name],
                "perishable": int(SUB_META[sub_name]["perishable"]),
                "update_time": "2026-10-16 18:00:00",
            })
    categories = pd.DataFrame(category_rows)

    # ---------------- 商品 ----------------
    total_subcategories = sum(len(v) for v in TOP_CATEGORIES.values())
    if n_skus < total_subcategories:
        raise ValueError(f"SKU 数量不能少于二级品类数 {total_subcategories}")
    base_counts = CATEGORY_PRODUCT_COUNT
    base_total = sum(base_counts.values())
    raw_counts = {top: base_counts[top] * n_skus / base_total for top in TOP_CATEGORIES}
    alloc_counts = {top: max(len(subs), int(raw_counts[top])) for top, subs in TOP_CATEGORIES.items()}
    remainder = n_skus - sum(alloc_counts.values())
    if remainder > 0:
        order = sorted(TOP_CATEGORIES, key=lambda t: (raw_counts[t] - int(raw_counts[t])), reverse=True)
        i = 0
        while remainder > 0:
            alloc_counts[order[i % len(order)]] += 1
            remainder -= 1
            i += 1
    elif remainder < 0:
        order = sorted(TOP_CATEGORIES, key=lambda t: alloc_counts[t], reverse=True)
        i = 0
        while remainder < 0:
            top = order[i % len(order)]
            if alloc_counts[top] > len(TOP_CATEGORIES[top]):
                alloc_counts[top] -= 1
                remainder += 1
            i += 1
            if i > 100000:
                break

    product_rows = []
    product_top = []
    product_seq = 1
    used_names: set[str] = set()
    for top_name, subs in TOP_CATEGORIES.items():
        counts = alloc_counts[top_name]
        base = counts // len(subs)
        remainder = counts % len(subs)
        top_brands = brand_by_top[top_name]
        top_suppliers = supplier_by_top[top_name]
        for s_idx, sub_name in enumerate(subs):
            n_products = base + (1 if s_idx < remainder else 0)
            if n_products == 0:
                continue
            meta = SUB_META[sub_name]
            sub_row = categories[(categories["category_name"] == sub_name) & (categories["level"] == 2)].iloc[0]
            low, high = meta["price"]
            for j in range(n_products):
                brand = top_brands.iloc[int(rng.integers(0, len(top_brands)))]
                supplier = top_suppliers.iloc[int(rng.integers(0, len(top_suppliers)))]
                item = meta["items"][int(rng.integers(0, len(meta["items"])))]
                spec = meta["specs"][int(rng.integers(0, len(meta["specs"])))]
                name = f"{brand['brand_name']}{item} {spec}"
                if name in used_names:
                    name = f"{name}（精选{int(rng.integers(1, 99))}）"
                used_names.add(name)
                # 对数分布，便宜商品更易成为高频动销品
                log_price = rng.uniform(np.log(max(low, 0.1)), np.log(max(high, low + 0.1)))
                list_price = round(float(np.exp(log_price)), 2)
                cost_ratio = rng.uniform(0.45, 0.72)
                cost_price = max(0.5, round(list_price * cost_ratio, 2))
                product_rows.append({
                    "product_id": f"P{product_seq:04d}",
                    "product_name": name,
                    "category_id": sub_row["category_id"],
                    "brand_id": brand["brand_id"],
                    "supplier_id": supplier["supplier_id"],
                    "list_price": list_price,
                    "cost_price": cost_price,
                    "unit": meta["unit"],
                    "spec": spec,
                    "shelf_life_days": int(meta["shelf"]),
                    "launch_date": str(date(2023, 1, 1) + timedelta(days=int(rng.integers(0, 1180)))),
                    "status": "在售",
                    "update_time": "2026-10-16 17:00:00",
                })
                product_top.append(top_name)
                product_seq += 1
    products = pd.DataFrame(product_rows)
    product_top_arr = np.array(product_top)
    product_price = products["list_price"].to_numpy(dtype=float)
    product_cost = products["cost_price"].to_numpy(dtype=float)

    # 商品基础热度：长尾 + 价格越低越动销 + 少量爆款
    base_weight = rng.lognormal(mean=0.0, sigma=0.9, size=len(products))
    med_price = np.median(product_price)
    base_weight *= (med_price / np.maximum(product_price, 0.1)) ** 0.35
    hero_idx = rng.choice(len(products), size=max(1, int(len(products) * 0.03)), replace=False)
    base_weight[hero_idx] *= 3.2
    base_weight = base_weight / base_weight.sum()

    # ---------------- 门店商品铺货与采样权重 ----------------
    assortment: dict[str, np.ndarray] = {}
    for _, store in stores.iterrows():
        loc_id = store["store_id"]
        store_type = store["store_type"]
        probs = ASSORT_PROB[store_type]
        mask = np.array([
            rng.random() < probs[product_top_arr[i]]
            for i in range(len(products))
        ])
        if store_type == "线上履约仓":
            mask = rng.random(len(products)) < 0.95
        idx = np.flatnonzero(mask)
        min_skus = 900 if store_type == "旗舰店" else 550 if store_type == "标准店" else 300 if store_type == "社区店" else 450 if store_type == "奥莱店" else 1200
        if len(idx) < min_skus:
            need = min_skus - len(idx)
            remaining = np.setdiff1d(np.arange(len(products)), idx)
            weights = base_weight[remaining] / base_weight[remaining].sum()
            extra = rng.choice(remaining, size=min(need, len(remaining)), replace=False, p=weights)
            idx = np.union1d(idx, extra)
        assortment[loc_id] = np.sort(idx)

    months = sorted({d.month for d in config.date_list()})
    sampling_weights: dict[tuple[str, int], np.ndarray] = {}
    for _, store in stores.iterrows():
        loc_id = store["store_id"]
        store_type = store["store_type"]
        aff = CATEGORY_AFFINITY[store_type]
        loci = assortment[loc_id]
        for month in months:
            w = base_weight[loci].copy()
            for k, p_idx in enumerate(loci):
                w[k] *= aff.get(product_top_arr[p_idx], 1.0)
                w[k] *= month_category_factor(product_top_arr[p_idx], month)
            w = w / w.sum()
            sampling_weights[(loc_id, month)] = w

    # ---------------- 会员 ----------------
    n_old = int(n_members * 0.10)
    n_mid = int(n_members * 0.25)
    n_recent = n_members - n_old - n_mid
    reg_dates = np.concatenate([
        _random_dates(rng, date(2024, 1, 1), date(2025, 4, 19), n_old),
        _random_dates(rng, date(2025, 4, 20), date(2025, 10, 16), n_mid),
        _random_dates(rng, date(2025, 10, 17), date(2026, 10, 16), n_recent),
    ])
    rng.shuffle(reg_dates)
    member_ids = np.array([f"M{i:07d}" for i in range(1, n_members + 1)])
    city_weights = np.array([c[5] for c in CITIES], dtype=float)
    city_weights = city_weights / city_weights.sum()
    member_city = rng.choice([c[0] for c in CITIES], size=n_members, p=city_weights)
    gender = rng.choice(["男", "女", "未知"], size=n_members, p=[0.47, 0.48, 0.05])
    ages = np.clip(rng.normal(36, 12, size=n_members), 18, 75).round().astype(int)
    age_groups = np.select(
        [ages < 25, ages < 35, ages < 45, ages < 55],
        ["18-24岁", "25-34岁", "35-44岁", "45-54岁"], default="55岁以上",
    )
    member_status = rng.choice(["正常", "沉睡", "注销"], size=n_members, p=[0.96, 0.03, 0.01])
    base_propensity = rng.lognormal(0.0, 0.9, size=n_members)
    q = np.quantile(base_propensity, [0.25, 0.5, 0.75])
    level = np.empty(n_members, dtype=object)
    level_p = {
        0: [0.875, 0.10, 0.02, 0.005],
        1: [0.75, 0.20, 0.05, 0.0],
        2: [0.48, 0.35, 0.15, 0.02],
        3: [0.18, 0.40, 0.30, 0.12],
    }
    levels = ["普通会员", "银卡会员", "金卡会员", "黑卡会员"]
    for qi in range(4):
        mask = (
            (base_propensity <= q[0]) if qi == 0 else
            (base_propensity > q[0]) & (base_propensity <= q[1]) if qi == 1 else
            (base_propensity > q[1]) & (base_propensity <= q[2]) if qi == 2 else
            (base_propensity > q[2])
        )
        level[mask] = rng.choice(levels, size=int(mask.sum()), p=level_p[qi])
    level_factor = {"普通会员": 1.0, "银卡会员": 1.25, "金卡会员": 1.60, "黑卡会员": 2.20}
    status_factor = np.where(member_status == "正常", 1.0, np.where(member_status == "沉睡", 0.35, 0.0))
    member_propensity = base_propensity * np.array([level_factor[x] for x in level]) * status_factor
    member_propensity[member_status == "注销"] = 0.0
    suffix = rng.integers(0, 10000, size=n_members)
    prefixes = rng.choice(["130", "131", "132", "135", "136", "137", "138", "139", "150", "151", "152", "155", "156", "157", "158", "159", "170", "171", "176", "177", "178", "180", "181", "182", "183", "185", "186", "187", "188", "189"], size=n_members)
    phone_masked = [f"{prefixes[i]}****{suffix[i]:04d}" for i in range(n_members)]
    birth_dates = np.array([date(2026, 10, 17) - timedelta(days=int(age * 365 + rng.integers(0, 365))) for age in ages])
    reg_channel = rng.choice(["门店", "小程序", "APP", "公众号", "电商平台"], size=n_members, p=[0.30, 0.35, 0.20, 0.10, 0.05])
    level_base_points = {"普通会员": 0, "银卡会员": 1200, "金卡会员": 4500, "黑卡会员": 12000}
    points = np.array([
        int(level_base_points[level[i]] + base_propensity[i] * rng.uniform(50, 500))
        for i in range(n_members)
    ])
    members = pd.DataFrame({
        "member_id": member_ids,
        "phone_masked": phone_masked,
        "gender": gender,
        "birth_date": [str(x) for x in birth_dates],
        "age_group": age_groups,
        "city_id": member_city,
        "register_date": [str(np.datetime64(x, "D")) for x in reg_dates],
        "register_channel": reg_channel,
        "member_level": level,
        "points": points,
        "member_status": member_status,
        "update_time": [f"{np.datetime64(x, 'D')} 09:00:00" for x in reg_dates],
    })
    members["_reg_ordinal"] = [np.datetime64(x, "D").astype(object).toordinal() for x in reg_dates]
    member_meta = {
        "member_id": members["member_id"].to_numpy(),
        "reg_ordinal": members["_reg_ordinal"].to_numpy(dtype=np.int64),
        "propensity": member_propensity,
        "level": members["member_level"].to_numpy(),
        "purchasable": (members["member_status"] != "注销").to_numpy(),
    }
    members = members.drop(columns=["_reg_ordinal"])

    # ---------------- 渠道 ----------------
    channels = pd.DataFrame({
        "channel_id": ["CH01", "CH02", "CH03", "CH04"],
        "channel_name": ["线下POS", "微信小程序", "APP", "第三方平台"],
        "channel_type": ["线下", "线上", "线上", "线上"],
        "update_time": "2026-01-01 00:00:00",
    })

    # ---------------- 促销活动 ----------------
    promos = [
        ("PR01", "五一欢乐购", "节日大促", "2026-05-01", "2026-05-05", 0.12, 200),
        ("PR02", "618年中大促", "节日大促", "2026-06-01", "2026-06-18", 0.18, 199),
        ("PR03", "端午安康", "节日促销", "2026-06-19", "2026-06-21", 0.10, 100),
        ("PR04", "中秋团圆节", "节日促销", "2026-09-25", "2026-09-27", 0.12, 150),
        ("PR05", "国庆黄金周", "节日大促", "2026-10-01", "2026-10-07", 0.15, 200),
    ]
    promo_rows = []
    for pid, name, ptype, start, end, rate, min_amt in promos:
        promo_rows.append({
            "promotion_id": pid, "promotion_name": name, "promo_type": ptype,
            "channel_scope": "全渠道", "start_date": start, "end_date": end,
            "discount_rate": rate, "min_amount": min_amt, "status": "生效",
            "update_time": f"{start} 00:00:00", "_member_only": 0,
        })
    for d in config.date_list():
        if d.day in (8, 18, 28) and d >= config.start_date:
            pid = f"PRM{d:%Y%m%d}"
            promo_rows.append({
                "promotion_id": pid, "promotion_name": f"会员日{d.month}月{d.day}日",
                "promo_type": "会员日", "channel_scope": "全渠道",
                "start_date": d.isoformat(), "end_date": d.isoformat(),
                "discount_rate": 0.08, "min_amount": 100, "status": "生效",
                "update_time": f"{d.isoformat()} 00:00:00", "_member_only": 1,
            })
    promotions = pd.DataFrame(promo_rows)
    promotions_by_date: dict[str, list[dict]] = {}
    # 日期 -> 活动（用于订单/会话生成）
    for _, p in promotions.iterrows():
        start = date.fromisoformat(p["start_date"])
        end = date.fromisoformat(p["end_date"])
        d = start
        while d <= end:
            promotions_by_date.setdefault(d.isoformat(), []).append(p.to_dict())
            d += timedelta(days=1)

    return {
        "stores": stores.drop(columns=["_base_footfall"]),
        "store_simulation": stores[["store_id", "store_type", "city_id", "is_offline", "_base_footfall"]].copy(),
        "suppliers": suppliers.drop(columns=[]),
        "brands": brands.drop(columns=["_top_category"]),
        "categories": categories,
        "products": products,
        "members": members,
        "channels": channels,
        "promotions": promotions.drop(columns=["_member_only"]),
        "promotions_by_date": promotions_by_date,
        "product_top_category": product_top_arr,
        "product_price": product_price,
        "product_cost": product_cost,
        "product_base_weight": base_weight,
        "assortment": assortment,
        "sampling_weights": sampling_weights,
        "member_meta": member_meta,
        "sub_to_top": sub_to_top,
    }
