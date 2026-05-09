import os
import json
import random
import time
import requests
import traceback
import sys
from PIL import Image, ImageDraw, ImageFont
import google.generativeai as genai
from moviepy.editor import ImageClip, concatenate_videoclips, CompositeVideoClip, VideoFileClip, vfx
import arabic_reshaper
from bidi.algorithm import get_display
from instagrapi import Client
from instagrapi.exceptions import ChallengeRequired # تمت الإضافة لالتقاط طلب التحقق من إنستقرام

# --- الإعدادات والمتغيرات البيئية ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")
IG_USERNAME = os.getenv("IG_USERNAME")
IG_PASSWORD = os.getenv("IG_PASSWORD")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

genai.configure(api_key=GEMINI_API_KEY)

FOLDERS_MAP = {
    "sh": "معاوز شحري",
    "ha": "معاوز حليسي"
}

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
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text[:4000]}
    requests.post(url, json=payload)

# --- دالة جديدة: إرسال الفيديو كملف لتليجرام ---
def send_telegram_video(video_path, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption[:1000]}
    try:
        with open(video_path, "rb") as video_file:
            files = {"video": video_file}
            requests.post(url, data=payload, files=files)
    except Exception as e:
        send_telegram_msg(f"⚠️ تنبيه: تعذر إرسال الفيديو لتليجرام، ولكن سيتم إكمال النشر.\nالخطأ: {str(e)}")

def generate_caption(types_used):
    try:
        model = genai.GenerativeModel('gemini-pro')
        types_str = " و ".join(types_used)
        prompt = f"اكتب وصف (Caption) جذاب وقصير لإنستقرام ريلز لحساب محل 'بازهير للمعاوز'. الفيديو يعرض {types_str}. ركز على الفخامة، الأصالة، واستخدم هاشتاقات مناسبة. لا تضع أي ردود غير الوصف نفسه."
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return "تشكيلة جديدة وفاخرة من بازهير للمعاوز. #معاوز #اليمن #بازهير"

def generate_video_hf(image_path, prompt):
    API_URL = "https://api-inference.huggingface.co/models/stabilityai/stable-video-diffusion-img2vid-xt"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    try:
        with open(image_path, "rb") as f:
            data = f.read()
        response = requests.post(API_URL, headers=headers, data=data, timeout=40)
        if response.status_code == 200:
            output_path = f"temp_{int(time.time())}.mp4"
            with open(output_path, "wb") as f:
                f.write(response.content)
            return output_path
        else:
            send_telegram_msg(f"⚠️ تنبيه: سيرفر الذكاء الاصطناعي للفيديو غير متاح حالياً (كود: {response.status_code}). جاري استخدام التحريك البديل.")
    except Exception as e:
        pass
    return None

def apply_ken_burns(image_path, duration=5):
    clip = ImageClip(image_path).set_duration(duration)
    clip = clip.resize(lambda t: 1 + 0.02 * t).set_position(('center', 'center'))
    return clip

def create_arabic_text_clip(text, size=(1080, 200), fontsize=70, font_path="taj.ttf"):
    if not os.path.exists(font_path):
        raise FileNotFoundError(f"ملف الخط '{font_path}' غير موجود في المشروع! يرجى التأكد من رفعه وتسميته بشكل صحيح.")

    reshaped_text = arabic_reshaper.reshape(text)
    bidi_text = get_display(reshaped_text)
    
    img = Image.new('RGBA', size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(font_path, fontsize)
    
    text_bbox = draw.textbbox((0, 0), bidi_text, font=font)
    text_w = text_bbox[2] - text_bbox[0]
    text_h = text_bbox[3] - text_bbox[1]
    x = (size[0] - text_w) / 2
    y = (size[1] - text_h) / 2
    
    draw.text((x+3, y+3), bidi_text, font=font, fill=(0,0,0,150))
    draw.text((x, y), bidi_text, font=font, fill=(255,255,255,255))
    
    img_path = f"temp_text_{int(time.time())}.png"
    img.save(img_path)
    return ImageClip(img_path)

def main():
    history = load_history()
    selected_images = []
    types_used = []
    
    base_img_dir = "images"
    sh_dir = os.path.join(base_img_dir, "sh")
    ha_dir = os.path.join(base_img_dir, "ha")
    
    sh_images = [os.path.join(sh_dir, img) for img in os.listdir(sh_dir) if img.endswith(('.jpg', '.png', '.jpeg')) and os.path.join(sh_dir, img) not in history] if os.path.exists(sh_dir) else []
    ha_images = [os.path.join(ha_dir, img) for img in os.listdir(ha_dir) if img.endswith(('.jpg', '.png', '.jpeg')) and os.path.join(ha_dir, img) not in history] if os.path.exists(ha_dir) else []
    
    random.shuffle(sh_images)
    random.shuffle(ha_images)
    
    if len(sh_images) + len(ha_images) < 3:
        send_telegram_msg("⚠️ تنبيه أستاذ محمد: لا توجد صور جديدة كافية في المجلدات لصناعة فيديو اليوم. الرجاء رفع صور جديدة.")
        return
        
    if sh_images:
        selected_images.append({"path": sh_images.pop(0), "type_name": FOLDERS_MAP["sh"]})
    if ha_images:
        selected_images.append({"path": ha_images.pop(0), "type_name": FOLDERS_MAP["ha"]})
        
    all_remaining = []
    for img in sh_images: all_remaining.append({"path": img, "type_name": FOLDERS_MAP["sh"]})
    for img in ha_images: all_remaining.append({"path": img, "type_name": FOLDERS_MAP["ha"]})
    
    random.shuffle(all_remaining)
    if all_remaining and len(selected_images) < 3:
        selected_images.append(all_remaining.pop(0))
        
    for item in selected_images:
        history.append(item["path"])
        types_used.append(item["type_name"])

    video_clips = []
    for item in selected_images:
        img_path = item["path"]
        type_name = item["type_name"]
        
        hf_vid_path = generate_video_hf(img_path, f"A cinematic slow pan of a traditional woven garment, high quality, keeping complex geometric patterns intact.")
        
        if hf_vid_path:
            clip = VideoFileClip(hf_vid_path).set_duration(5).resize(height=1920, width=1080)
        else:
            clip = apply_ken_burns(img_path, duration=5).resize(height=1920, width=1080)
            
        clip = clip.fx(vfx.fadein, 0.5).fx(vfx.fadeout, 0.5)
        
        txt_clip = create_arabic_text_clip(type_name, font_path="taj.ttf")
        txt_clip = txt_clip.set_position(('center', 0.8), relative=True).set_duration(4).set_start(0.5).crossfadein(0.5).crossfadeout(0.5)
        
        video_clips.append(CompositeVideoClip([clip, txt_clip]))

    final_video = concatenate_videoclips(video_clips, method="compose")
    
    if os.path.exists("logo.png"):
        logo = ImageClip("logo.png").resize(height=100).margin(left=30, top=30, opacity=0).set_position(("left", "top")).set_duration(final_video.duration)
        final_video = CompositeVideoClip([final_video, logo])

    output_filename = f"bazheer_reel_{int(time.time())}.mp4"
    final_video.write_videofile(output_filename, fps=24, codec="libx264", audio_codec="aac")

    # --- تحديث جذري لقسم إنستقرام ليتصرف كتطبيق هاتف ويدعم الانتظار ---
    cl = Client()
    
    # محاكاة إعدادات الهاتف في اليمن لتفادي الحظر
    cl.set_country("YE")
    cl.set_timezone_offset(3 * 3600)
    cl.set_locale("ar_AE")
    
    if os.path.exists("session.json"):
        cl.load_settings("session.json")
        
    try:
        try:
            cl.login(IG_USERNAME, IG_PASSWORD)
        except ChallengeRequired:
            # حالة: إنستقرام يطلب تأكيد الهوية رسمياً
            send_telegram_msg("⚠️ تنبيه أستاذ محمد: إنستقرام يطلب التحقق من هويتك لدواعي أمنية. يرجى فتح التطبيق أو إيميلك الآن والموافقة (الضغط على 'هذا أنا' / 'This was me'). الكود سينتظر 90 ثانية ثم يكمل...")
            time.sleep(90)
            cl.login(IG_USERNAME, IG_PASSWORD)
        except Exception as e:
            # حالة: رسالة البريد الإلكتروني المشبوهة
            if "We can send you an email" in str(e) or "suspicious" in str(e).lower():
                send_telegram_msg("⚠️ تنبيه أستاذ محمد: إنستقرام أوقف الدخول وطلب التحقق. يرجى فتح التطبيق أو إيميلك الآن والموافقة. الكود سينتظر 90 ثانية ثم يحاول الإكمال...")
                time.sleep(90)
                cl.login(IG_USERNAME, IG_PASSWORD)
            else:
                raise e

        cl.dump_settings("session.json")
        caption = generate_caption(list(set(types_used)))
        
        # 1. إرسال الفيديو إلى تليجرام أولاً
        send_telegram_msg("⏳ جاري إرسال الفيديو المصنوع إلى تليجرام لمعاينته...")
        send_telegram_video(output_filename, f"🎥 الفيديو الجاهز للنشر\n\nالوصف المقترح:\n{caption}")
        
        # 2. النشر على إنستقرام
        media = cl.clip_upload(output_filename, caption)
        
        # 3. حفظ السجل وإرسال رابط المقطع
        save_history(history)
        reel_url = f"https://www.instagram.com/reel/{media.code}/" if hasattr(media, 'code') else "تم النشر بنجاح."
        send_telegram_msg(f"✅ أهلاً أستاذ محمد، تم بحمد الله نشر مقطع اليوم بنجاح على حساب بازهير للمعاوز!\n\nرابط المقطع:\n{reel_url}")
        
    except Exception as e:
        send_telegram_msg(f"❌ عذراً أستاذ محمد، حدث خطأ أثناء عملية النشر على إنستقرام:\n{str(e)}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        error_details = traceback.format_exc()
        error_msg = f"❌ أهلاً أستاذ محمد، حدث خطأ برمجي:\n\n{str(e)}\n\nالتفاصيل:\n{error_details[:500]}"
        send_telegram_msg(error_msg)
        sys.exit(1)
