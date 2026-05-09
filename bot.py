import os
import json
import random
import time
import requests
from PIL import Image, ImageDraw, ImageFont
import google.generativeai as genai
from moviepy.editor import ImageClip, concatenate_videoclips, CompositeVideoClip, VideoFileClip, AudioFileClip, vfx
import arabic_reshaper
from bidi.algorithm import get_display
from instagrapi import Client

# --- الإعدادات والمتغيرات البيئية ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")
IG_USERNAME = os.getenv("IG_USERNAME")
IG_PASSWORD = os.getenv("IG_PASSWORD")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

genai.configure(api_key=GEMINI_API_KEY)

# قاموس مسميات المجلدات
FOLDERS_MAP = {
    "sh": "معاوز شحري",
    "ha": "معاوز حليسي",
    "sa": "معاوز صنعاني",
    "lah": "معاوز لحجي"
}

# --- دوال المساعدة (History & Telegram) ---
def load_history():
    if os.path.exists("history.json"):
        with open("history.json", "r") as f:
            return json.load(f)
    return []

def save_history(history):
    with open("history.json", "w") as f:
        json.dump(history, f)

def send_telegram_msg(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    requests.post(url, json=payload)

# --- دوال الذكاء الاصطناعي (Gemini & HF) ---
def generate_caption(types_used):
    model = genai.GenerativeModel('gemini-pro')
    types_str = " و ".join(types_used)
    prompt = f"اكتب وصف (Caption) جذاب وقصير لإنستقرام ريلز لحساب محل 'بازهير للمعاوز'. الفيديو يعرض {types_str}. ركز على الفخامة، الأصالة، واستخدم هاشتاقات مناسبة. لا تضع أي ردود غير الوصف نفسه."
    response = model.generate_content(prompt)
    return response.text

def generate_video_hf(image_path, prompt):
    # محاولة الاتصال بـ Hugging Face API لتوليد الفيديو (تتطلب API يدعم Image-to-Video)
    # نظراً لأن الـ APIs المجانية تتغير، نضع طلب قياسي، وفي حال الفشل ننتقل فوراً لخطة الطوارئ
    API_URL = "https://api-inference.huggingface.co/models/stabilityai/stable-video-diffusion-img2vid"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    try:
        with open(image_path, "rb") as f:
            data = f.read()
        response = requests.post(API_URL, headers=headers, data=data, timeout=30)
        if response.status_code == 200:
            output_path = f"temp_{int(time.time())}.mp4"
            with open(output_path, "wb") as f:
                f.write(response.content)
            return output_path
    except Exception as e:
        print(f"Hugging Face API failed: {e}. Switching to Fallback (Ken Burns).")
    return None

# --- خطة الطوارئ: تحريك الصور سينمائياً بـ MoviePy ---
def apply_ken_burns(image_path, duration=5):
    clip = ImageClip(image_path).set_duration(duration)
    # تأثير تقريب بطيء يعطي طابعاً سينمائياً
    clip = clip.resize(lambda t: 1 + 0.02 * t).set_position(('center', 'center'))
    return clip

# --- إنشاء نصوص عربية صحيحة (لتفادي مشكلة ImageMagick في السيرفرات) ---
def create_arabic_text_clip(text, size=(1080, 200), fontsize=70, font_path="font.ttf"):
    reshaped_text = arabic_reshaper.reshape(text)
    bidi_text = get_display(reshaped_text)
    
    img = Image.new('RGBA', size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(font_path, fontsize)
    except:
        font = ImageFont.load_default()
    
    # توسيط النص
    text_bbox = draw.textbbox((0, 0), bidi_text, font=font)
    text_w = text_bbox[2] - text_bbox[0]
    text_h = text_bbox[3] - text_bbox[1]
    x = (size[0] - text_w) / 2
    y = (size[1] - text_h) / 2
    
    # رسم النص مع ظل ليكون واضحاً
    draw.text((x+3, y+3), bidi_text, font=font, fill=(0,0,0,150))
    draw.text((x, y), bidi_text, font=font, fill=(255,255,255,255))
    
    img_path = f"temp_text_{int(time.time())}.png"
    img.save(img_path)
    return ImageClip(img_path)

# --- المسار الرئيسي للعمل ---
def main():
    history = load_history()
    selected_images = []
    types_used = []
    
    # 1. اختيار 3 صور من مجلدات مختلفة لم تستخدم مسبقاً
    base_img_dir = "images"
    folders = [f for f in os.listdir(base_img_dir) if os.path.isdir(os.path.join(base_img_dir, f))]
    random.shuffle(folders)
    
    for folder in folders:
        if len(selected_images) >= 3:
            break
        folder_path = os.path.join(base_img_dir, folder)
        images = [i for i in os.listdir(folder_path) if i.endswith(('.jpg', '.png', '.jpeg'))]
        random.shuffle(images)
        for img in images:
            img_full_path = os.path.join(folder_path, img)
            if img_full_path not in history:
                selected_images.append({
                    "path": img_full_path,
                    "type_name": FOLDERS_MAP.get(folder, "معاوز يمنية فاخرة")
                })
                history.append(img_full_path)
                types_used.append(FOLDERS_MAP.get(folder, "بازهير"))
                break

    if len(selected_images) < 3:
        send_telegram_msg("⚠️ تنبيه أستاذ محمد: لا يوجد صور جديدة كافية في المجلدات لصناعة الريل.")
        return

    # 2. معالجة الفيديوهات
    video_clips = []
    for item in selected_images:
        img_path = item["path"]
        type_name = item["type_name"]
        
        # محاولة ذكاء اصطناعي، وإذا فشل نستخدم خطة الطوارئ
        hf_vid_path = generate_video_hf(img_path, f"A cinematic slow pan of a traditional woven garment, high quality, keeping complex geometric patterns intact.")
        
        if hf_vid_path:
            clip = VideoFileClip(hf_vid_path).set_duration(5).resize(height=1920, width=1080)
        else:
            clip = apply_ken_burns(img_path, duration=5).resize(height=1920, width=1080)
            
        # إضافة تأثير التلاشي للمقطع
        clip = clip.fx(vfx.fadein, 0.5).fx(vfx.fadeout, 0.5)
        
        # إنشاء النص العربي وإضافته أسفل الشاشة مع التلاشي
        txt_clip = create_arabic_text_clip(type_name, font_path="font.ttf")
        txt_clip = txt_clip.set_position(('center', 0.8), relative=True).set_duration(4).set_start(0.5).crossfadein(0.5).crossfadeout(0.5)
        
        video_clips.append(CompositeVideoClip([clip, txt_clip]))

    # 3. دمج المقاطع
    final_video = concatenate_videoclips(video_clips, method="compose")
    
    # إضافة شعار بازهير (صغير جداً في أعلى اليسار)
    if os.path.exists("logo.png"):
        logo = ImageClip("logo.png").resize(height=100).margin(left=30, top=30, opacity=0).set_position(("left", "top")).set_duration(final_video.duration)
        final_video = CompositeVideoClip([final_video, logo])

    # 4. التصدير النهائي
    output_filename = f"bazheer_reel_{int(time.time())}.mp4"
    final_video.write_videofile(output_filename, fps=24, codec="libx264", audio_codec="aac")

    # 5. النشر على إنستقرام مع إدارة الجلسات لتفادي الحظر
    cl = Client()
    if os.path.exists("session.json"):
        cl.load_settings("session.json")
    try:
        cl.login(IG_USERNAME, IG_PASSWORD)
        cl.dump_settings("session.json")
        
        caption = generate_caption(list(set(types_used)))
        
        # النشر (ملاحظة: سيتم رفع الفيديو كما هو، وفي حال رغبت بربطه بصوت عبر IG يتم تمرير audio_id هنا في إعدادات متقدمة)
        media = cl.clip_upload(output_filename, caption)
        
        # 6. تحديث التاريخ وإرسال التقرير
        save_history(history)
        send_telegram_msg(f"✅ أهلاً أستاذ محمد، تم بحمد الله تجهيز ونشر مقطع اليوم بنجاح على حساب بازهير للمعاوز!\n\nالوصف المستخدم:\n{caption}")
        
    except Exception as e:
        send_telegram_msg(f"❌ عذراً أستاذ محمد، حدث خطأ أثناء النشر:\n{str(e)}")

if __name__ == "__main__":
    main()
