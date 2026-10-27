from schemas.catalog import Course


broadcast = Course.model_validate({
    "project_type": "broadcast",
    "title": "广播词示范课程",
    "lessons": [
        {
            "title": "欢迎词",
            "order": 1,
            "content": {
                "template_type": "broadcast",
                "chinese_text": "女士们，先生们，欢迎您乘坐本次航班。",
                "english_text": "Ladies and gentlemen, welcome aboard.",
                "key_words": [
                    {
                        "word": "aboard",
                        "meaning": "在飞机上"
                    }
                ]
            }
        }
    ]
})

caet2 = Course.model_validate({
    "project_type": "caet2",
    "title": "CAET2 示范课程",
    "lessons": [
        {
            "title": "特殊餐食",
            "order": 1,
            "content": {
                "template_type": "caet2",
                "scenario": "与旅客确认特殊餐食",
                "chinese_prompt": "我可以跟您确认一下您的特殊餐食吗？",
                "standard_english": "May I confirm your special meal request with you?"
            }
        }
    ]
})

caet3 = Course.model_validate({
    "project_type": "caet3",
    "title": "CAET3 示范课程",
    "lessons": [
        {
            "title": "航班延误转述",
            "order": 1,
            "content": {
                "template_type": "caet3",
                "scenario": "航班延误",
                "chinese_task": "因天气原因，航班预计延误30分钟。",
                "reference_english": "Due to the weather conditions, the flight is expected to be delayed for about 30 minutes.",
                "key_points": [
                    "天气原因",
                    "延误30分钟"
                ]
            }
        }
    ]
})

print("broadcast:", broadcast.lessons[0].content.template_type)
print("caet2:", caet2.lessons[0].content.template_type)
print("caet3:", caet3.lessons[0].content.template_type)
print("Three course templates OK")
