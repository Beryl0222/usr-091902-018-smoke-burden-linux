"""国家与地区目录数据（ISO 3166-1 alpha-2）。

每项为 ``(代码, 名称, UN 次区域, WHO 区域)``。地区映射以带版本的目录为唯一来源，
运行清单记录所使用的映射版本。
"""

# UN 次区域
AF_N = "非洲-北部"
AF_E = "非洲-东部"
AF_M = "非洲-中部"
AF_S = "非洲-南部"
AF_W = "非洲-西部"
AM_CAR = "美洲-加勒比"
AM_CEN = "美洲-中美"
AM_S = "美洲-南美"
AM_N = "美洲-北美"
EU_E = "欧洲-东欧"
EU_N = "欧洲-北欧"
EU_S = "欧洲-南欧"
EU_W = "欧洲-西欧"
AS_C = "亚洲-中亚"
AS_E = "亚洲-东亚"
AS_SE = "亚洲-东南亚"
AS_S = "亚洲-南亚"
AS_W = "亚洲-西亚"
OC_A = "大洋洲-澳新"
OC_MEL = "大洋洲-美拉尼西亚"
OC_MIC = "大洋洲-密克罗尼西亚"
OC_POL = "大洋洲-波利尼西亚"
POLAR = "极地"

WHO_AFRO = "AFRO"
WHO_AMRO = "AMRO"
WHO_EMRO = "EMRO"
WHO_EURO = "EURO"
WHO_SEAR = "SEARO"
WHO_WPR = "WPR"

COUNTRY_ROWS = [
    # —— 非洲北部 ——
    ("DZ", "阿尔及利亚", AF_N, WHO_AFRO),
    ("EG", "埃及", AF_N, WHO_EMRO),
    ("EH", "西撒哈拉", AF_N, WHO_AFRO),
    ("LY", "利比亚", AF_N, WHO_EMRO),
    ("MA", "摩洛哥", AF_N, WHO_EMRO),
    ("SD", "苏丹", AF_N, WHO_EMRO),
    ("TN", "突尼斯", AF_N, WHO_EMRO),
    # —— 非洲东部 ——
    ("BI", "布隆迪", AF_E, WHO_AFRO),
    ("KM", "科摩罗", AF_E, WHO_AFRO),
    ("DJ", "吉布提", AF_E, WHO_EMRO),
    ("ER", "厄立特里亚", AF_E, WHO_AFRO),
    ("ET", "埃塞俄比亚", AF_E, WHO_AFRO),
    ("IO", "英属印度洋领地", AF_E, WHO_AFRO),
    ("KE", "肯尼亚", AF_E, WHO_AFRO),
    ("MG", "马达加斯加", AF_E, WHO_AFRO),
    ("MW", "马拉维", AF_E, WHO_AFRO),
    ("MU", "毛里求斯", AF_E, WHO_AFRO),
    ("YT", "马约特", AF_E, WHO_AFRO),
    ("MZ", "莫桑比克", AF_E, WHO_AFRO),
    ("RE", "留尼汪", AF_E, WHO_AFRO),
    ("RW", "卢旺达", AF_E, WHO_AFRO),
    ("SC", "塞舌尔", AF_E, WHO_AFRO),
    ("SO", "索马里", AF_E, WHO_EMRO),
    ("SS", "南苏丹", AF_E, WHO_AFRO),
    ("UG", "乌干达", AF_E, WHO_AFRO),
    ("TZ", "坦桑尼亚联合共和国", AF_E, WHO_AFRO),
    ("ZM", "赞比亚", AF_E, WHO_AFRO),
    ("ZW", "津巴布韦", AF_E, WHO_AFRO),
    # —— 非洲中部 ——
    ("AO", "安哥拉", AF_M, WHO_AFRO),
    ("CM", "喀麦隆", AF_M, WHO_AFRO),
    ("CF", "中非共和国", AF_M, WHO_AFRO),
    ("TD", "乍得", AF_M, WHO_AFRO),
    ("CG", "刚果（布）", AF_M, WHO_AFRO),
    ("CD", "刚果（金）", AF_M, WHO_AFRO),
    ("GQ", "赤道几内亚", AF_M, WHO_AFRO),
    ("GA", "加蓬", AF_M, WHO_AFRO),
    ("ST", "圣多美和普林西比", AF_M, WHO_AFRO),
    # —— 非洲南部 ——
    ("BW", "博茨瓦纳", AF_S, WHO_AFRO),
    ("SZ", "斯威士兰", AF_S, WHO_AFRO),
    ("LS", "莱索托", AF_S, WHO_AFRO),
    ("NA", "纳米比亚", AF_S, WHO_AFRO),
    ("ZA", "南非", AF_S, WHO_AFRO),
    # —— 非洲西部 ——
    ("BJ", "贝宁", AF_W, WHO_AFRO),
    ("BF", "布基纳法索", AF_W, WHO_AFRO),
    ("CV", "佛得角", AF_W, WHO_AFRO),
    ("CI", "科特迪瓦", AF_W, WHO_AFRO),
    ("GM", "冈比亚", AF_W, WHO_AFRO),
    ("GH", "加纳", AF_W, WHO_AFRO),
    ("GN", "几内亚", AF_W, WHO_AFRO),
    ("GW", "几内亚比绍", AF_W, WHO_AFRO),
    ("LR", "利比里亚", AF_W, WHO_AFRO),
    ("ML", "马里", AF_W, WHO_AFRO),
    ("MR", "毛里塔尼亚", AF_W, WHO_AFRO),
    ("NE", "尼日尔", AF_W, WHO_AFRO),
    ("NG", "尼日利亚", AF_W, WHO_AFRO),
    ("SH", "圣赫勒拿", AF_W, WHO_AFRO),
    ("SN", "塞内加尔", AF_W, WHO_AFRO),
    ("SL", "塞拉利昂", AF_W, WHO_AFRO),
    ("TG", "多哥", AF_W, WHO_AFRO),
    # —— 加勒比 ——
    ("AI", "安圭拉", AM_CAR, WHO_AMRO),
    ("AG", "安提瓜和巴布达", AM_CAR, WHO_AMRO),
    ("AW", "阿鲁巴", AM_CAR, WHO_AMRO),
    ("BS", "巴哈马", AM_CAR, WHO_AMRO),
    ("BB", "巴巴多斯", AM_CAR, WHO_AMRO),
    ("BQ", "博奈尔、圣尤斯特歇斯和萨巴", AM_CAR, WHO_AMRO),
    ("VG", "英属维尔京群岛", AM_CAR, WHO_AMRO),
    ("KY", "开曼群岛", AM_CAR, WHO_AMRO),
    ("CU", "古巴", AM_CAR, WHO_AMRO),
    ("CW", "库拉索", AM_CAR, WHO_AMRO),
    ("DM", "多米尼克", AM_CAR, WHO_AMRO),
    ("DO", "多米尼加共和国", AM_CAR, WHO_AMRO),
    ("GD", "格林纳达", AM_CAR, WHO_AMRO),
    ("GP", "瓜德罗普", AM_CAR, WHO_AMRO),
    ("HT", "海地", AM_CAR, WHO_AMRO),
    ("JM", "牙买加", AM_CAR, WHO_AMRO),
    ("MQ", "马提尼克", AM_CAR, WHO_AMRO),
    ("MS", "蒙特塞拉特", AM_CAR, WHO_AMRO),
    ("PR", "波多黎各", AM_CAR, WHO_AMRO),
    ("BL", "圣巴泰勒米", AM_CAR, WHO_AMRO),
    ("KN", "圣基茨和尼维斯", AM_CAR, WHO_AMRO),
    ("LC", "圣卢西亚", AM_CAR, WHO_AMRO),
    ("MF", "法属圣马丁", AM_CAR, WHO_AMRO),
    ("PM", "圣皮埃尔和密克隆", AM_CAR, WHO_AMRO),
    ("VC", "圣文森特和格林纳丁斯", AM_CAR, WHO_AMRO),
    ("SX", "荷属圣马丁", AM_CAR, WHO_AMRO),
    ("TT", "特立尼达和多巴哥", AM_CAR, WHO_AMRO),
    ("TC", "特克斯和凯科斯群岛", AM_CAR, WHO_AMRO),
    ("VI", "美属维尔京群岛", AM_CAR, WHO_AMRO),
    # —— 中美 ——
    ("BZ", "伯利兹", AM_CEN, WHO_AMRO),
    ("CR", "哥斯达黎加", AM_CEN, WHO_AMRO),
    ("SV", "萨尔瓦多", AM_CEN, WHO_AMRO),
    ("GT", "危地马拉", AM_CEN, WHO_AMRO),
    ("HN", "洪都拉斯", AM_CEN, WHO_AMRO),
    ("NI", "尼加拉瓜", AM_CEN, WHO_AMRO),
    ("PA", "巴拿马", AM_CEN, WHO_AMRO),
    # —— 南美 ——
    ("AR", "阿根廷", AM_S, WHO_AMRO),
    ("BO", "玻利维亚", AM_S, WHO_AMRO),
    ("BR", "巴西", AM_S, WHO_AMRO),
    ("CL", "智利", AM_S, WHO_AMRO),
    ("CO", "哥伦比亚", AM_S, WHO_AMRO),
    ("EC", "厄瓜多尔", AM_S, WHO_AMRO),
    ("FK", "马尔维纳斯群岛", AM_S, WHO_AMRO),
    ("GF", "法属圭亚那", AM_S, WHO_AMRO),
    ("GY", "圭亚那", AM_S, WHO_AMRO),
    ("PY", "巴拉圭", AM_S, WHO_AMRO),
    ("PE", "秘鲁", AM_S, WHO_AMRO),
    ("SR", "苏里南", AM_S, WHO_AMRO),
    ("UY", "乌拉圭", AM_S, WHO_AMRO),
    ("VE", "委内瑞拉", AM_S, WHO_AMRO),
    # —— 北美 ——
    ("BM", "百慕大", AM_N, WHO_AMRO),
    ("CA", "加拿大", AM_N, WHO_AMRO),
    ("GL", "格陵兰", AM_N, WHO_AMRO),
    ("US", "美国", AM_N, WHO_AMRO),
    # —— 东欧 ——
    ("BY", "白俄罗斯", EU_E, WHO_EURO),
    ("BG", "保加利亚", EU_E, WHO_EURO),
    ("CZ", "捷克", EU_E, WHO_EURO),
    ("HU", "匈牙利", EU_E, WHO_EURO),
    ("PL", "波兰", EU_E, WHO_EURO),
    ("MD", "摩尔多瓦共和国", EU_E, WHO_EURO),
    ("RO", "罗马尼亚", EU_E, WHO_EURO),
    ("RU", "俄罗斯联邦", EU_E, WHO_EURO),
    ("SK", "斯洛伐克", EU_E, WHO_EURO),
    ("UA", "乌克兰", EU_E, WHO_EURO),
    # —— 北欧 ——
    ("AX", "奥兰群岛", EU_N, WHO_EURO),
    ("DK", "丹麦", EU_N, WHO_EURO),
    ("EE", "爱沙尼亚", EU_N, WHO_EURO),
    ("FO", "法罗群岛", EU_N, WHO_EURO),
    ("FI", "芬兰", EU_N, WHO_EURO),
    ("GG", "根西", EU_N, WHO_EURO),
    ("IS", "冰岛", EU_N, WHO_EURO),
    ("IE", "爱尔兰", EU_N, WHO_EURO),
    ("IM", "马恩岛", EU_N, WHO_EURO),
    ("JE", "泽西", EU_N, WHO_EURO),
    ("LV", "拉脱维亚", EU_N, WHO_EURO),
    ("LT", "立陶宛", EU_N, WHO_EURO),
    ("NO", "挪威", EU_N, WHO_EURO),
    ("SJ", "斯瓦尔巴和扬马延", EU_N, WHO_EURO),
    ("SE", "瑞典", EU_N, WHO_EURO),
    ("GB", "英国", EU_N, WHO_EURO),
    # —— 南欧 ——
    ("AL", "阿尔巴尼亚", EU_S, WHO_EURO),
    ("AD", "安道尔", EU_S, WHO_EURO),
    ("BA", "波黑", EU_S, WHO_EURO),
    ("HR", "克罗地亚", EU_S, WHO_EURO),
    ("GI", "直布罗陀", EU_S, WHO_EURO),
    ("GR", "希腊", EU_S, WHO_EURO),
    ("VA", "梵蒂冈", EU_S, WHO_EURO),
    ("IT", "意大利", EU_S, WHO_EURO),
    ("MK", "北马其顿", EU_S, WHO_EURO),
    ("MT", "马耳他", EU_S, WHO_EURO),
    ("ME", "黑山", EU_S, WHO_EURO),
    ("PT", "葡萄牙", EU_S, WHO_EURO),
    ("SM", "圣马力诺", EU_S, WHO_EURO),
    ("RS", "塞尔维亚", EU_S, WHO_EURO),
    ("SI", "斯洛文尼亚", EU_S, WHO_EURO),
    ("ES", "西班牙", EU_S, WHO_EURO),
    # —— 西欧 ——
    ("AT", "奥地利", EU_W, WHO_EURO),
    ("BE", "比利时", EU_W, WHO_EURO),
    ("FR", "法国", EU_W, WHO_EURO),
    ("DE", "德国", EU_W, WHO_EURO),
    ("LI", "列支敦士登", EU_W, WHO_EURO),
    ("LU", "卢森堡", EU_W, WHO_EURO),
    ("MC", "摩纳哥", EU_W, WHO_EURO),
    ("NL", "荷兰", EU_W, WHO_EURO),
    ("CH", "瑞士", EU_W, WHO_EURO),
    # —— 中亚 ——
    ("KZ", "哈萨克斯坦", AS_C, WHO_EURO),
    ("KG", "吉尔吉斯斯坦", AS_C, WHO_EURO),
    ("TJ", "塔吉克斯坦", AS_C, WHO_EURO),
    ("TM", "土库曼斯坦", AS_C, WHO_EURO),
    ("UZ", "乌兹别克斯坦", AS_C, WHO_EURO),
    # —— 东亚 ——
    ("CN", "中国", AS_E, WHO_WPR),
    ("HK", "中国香港特别行政区", AS_E, WHO_WPR),
    ("JP", "日本", AS_E, WHO_WPR),
    ("KP", "朝鲜民主主义人民共和国", AS_E, WHO_SEAR),
    ("KR", "韩国", AS_E, WHO_WPR),
    ("MO", "中国澳门特别行政区", AS_E, WHO_WPR),
    ("MN", "蒙古", AS_E, WHO_WPR),
    ("TW", "中国台湾地区", AS_E, WHO_WPR),
    # —— 东南亚 ——
    ("BN", "文莱达鲁萨兰国", AS_SE, WHO_WPR),
    ("KH", "柬埔寨", AS_SE, WHO_WPR),
    ("ID", "印度尼西亚", AS_SE, WHO_SEAR),
    ("LA", "老挝", AS_SE, WHO_WPR),
    ("MY", "马来西亚", AS_SE, WHO_WPR),
    ("MM", "缅甸", AS_SE, WHO_SEAR),
    ("PH", "菲律宾", AS_SE, WHO_WPR),
    ("SG", "新加坡", AS_SE, WHO_WPR),
    ("TH", "泰国", AS_SE, WHO_SEAR),
    ("TL", "东帝汶", AS_SE, WHO_SEAR),
    ("VN", "越南", AS_SE, WHO_WPR),
    # —— 南亚 ——
    ("AF", "阿富汗", AS_S, WHO_EMRO),
    ("BD", "孟加拉国", AS_S, WHO_SEAR),
    ("BT", "不丹", AS_S, WHO_SEAR),
    ("IN", "印度", AS_S, WHO_SEAR),
    ("IR", "伊朗", AS_S, WHO_EMRO),
    ("MV", "马尔代夫", AS_S, WHO_SEAR),
    ("NP", "尼泊尔", AS_S, WHO_SEAR),
    ("PK", "巴基斯坦", AS_S, WHO_EMRO),
    ("LK", "斯里兰卡", AS_S, WHO_SEAR),
    # —— 西亚 ——
    ("AM", "亚美尼亚", AS_W, WHO_EURO),
    ("AZ", "阿塞拜疆", AS_W, WHO_EURO),
    ("BH", "巴林", AS_W, WHO_EMRO),
    ("CY", "塞浦路斯", AS_W, WHO_EURO),
    ("GE", "格鲁吉亚", AS_W, WHO_EURO),
    ("IQ", "伊拉克", AS_W, WHO_EMRO),
    ("IL", "以色列", AS_W, WHO_EURO),
    ("JO", "约旦", AS_W, WHO_EMRO),
    ("KW", "科威特", AS_W, WHO_EMRO),
    ("LB", "黎巴嫩", AS_W, WHO_EMRO),
    ("OM", "阿曼", AS_W, WHO_EMRO),
    ("PS", "巴勒斯坦", AS_W, WHO_EMRO),
    ("QA", "卡塔尔", AS_W, WHO_EMRO),
    ("SA", "沙特阿拉伯", AS_W, WHO_EMRO),
    ("SY", "叙利亚", AS_W, WHO_EMRO),
    ("TR", "土耳其", AS_W, WHO_EURO),
    ("AE", "阿拉伯联合酋长国", AS_W, WHO_EMRO),
    ("YE", "也门", AS_W, WHO_EMRO),
    # —— 澳新 ——
    ("AU", "澳大利亚", OC_A, WHO_WPR),
    ("NZ", "新西兰", OC_A, WHO_WPR),
    ("NF", "诺福克岛", OC_A, WHO_WPR),
    # —— 美拉尼西亚 ——
    ("FJ", "斐济", OC_MEL, WHO_WPR),
    ("NC", "新喀里多尼亚", OC_MEL, WHO_WPR),
    ("PG", "巴布亚新几内亚", OC_MEL, WHO_WPR),
    ("SB", "所罗门群岛", OC_MEL, WHO_WPR),
    ("VU", "瓦努阿图", OC_MEL, WHO_WPR),
    # —— 密克罗尼西亚 ——
    ("GU", "关岛", OC_MIC, WHO_WPR),
    ("KI", "基里巴斯", OC_MIC, WHO_WPR),
    ("MH", "马绍尔群岛", OC_MIC, WHO_WPR),
    ("FM", "密克罗尼西亚联邦", OC_MIC, WHO_WPR),
    ("NR", "瑙鲁", OC_MIC, WHO_WPR),
    ("MP", "北马里亚纳群岛", OC_MIC, WHO_WPR),
    ("PW", "帕劳", OC_MIC, WHO_WPR),
    # —— 波利尼西亚 ——
    ("AS", "美属萨摩亚", OC_POL, WHO_WPR),
    ("CK", "库克群岛", OC_POL, WHO_WPR),
    ("PF", "法属波利尼西亚", OC_POL, WHO_WPR),
    ("NU", "纽埃", OC_POL, WHO_WPR),
    ("PN", "皮特凯恩群岛", OC_POL, WHO_WPR),
    ("WS", "萨摩亚", OC_POL, WHO_WPR),
    ("TK", "托克劳", OC_POL, WHO_WPR),
    ("TO", "汤加", OC_POL, WHO_WPR),
    ("TV", "图瓦卢", OC_POL, WHO_WPR),
    ("WF", "瓦利斯和富图纳", OC_POL, WHO_WPR),
    # —— 极地 ——
    ("AQ", "南极洲", POLAR, ""),
]
