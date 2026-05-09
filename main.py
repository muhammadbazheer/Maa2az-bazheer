import os
import json
import random
import time
import requests
import traceback
import sys
import shutil
import subprocess
from PIL import Image, ImageDraw, ImageFont, ImageOps
import google.generativeai as genai
from moviepy.editor import ImageClip, concatenate_videoclips, CompositeVideoClip, VideoFileClip, vfx
import arabic_reshaper
from bidi.algorithm import get_display

# استدعاء مكتبات إنستقرام وذكاء الفيديو
from instagrapi import Client as InstaClient
from instagrapi.exceptions import ChallengeRequired
from gradio_client import Client as GradioClient, handle_file

# --- الإعدادات والمتغيرات البيئية ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
IG_USERNAME = os.getenv("IG_USERNAME")
IG_PASSWORD = os.getenv("IG_PASSWORD")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

genai.configure(api_key=GEMINI_API_KEY)

FOLDERS_MAP = {
    "sh": "معاوز شحري",
    "ha": "معاوز حليسي"
}

# --- دوال المساعدة والسجلات ---
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

def send_telegram_video(video_path, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption[:1000]}
    try:
        with open(video_path, "rb") as video_file:
            files = {"video": video_file}
            requests.post(url, data=payload, files=files)
    except Exception as e:
        send_telegram_msg(f"⚠️ تنبيه: تعذر إرسال الفيديو لتليجرام لمعاينته.\nالخطأ: {str(e)}")

# الحل العبقري لحفظ الجلسة من داخل بايثون لتفادي حظر إنستقرام
def commit_state_to_github():
    try:
        os.system('git config --global user.name "github-actions[bot]"')
        os.system('git config --global user.email "github-actions[bot]@users.noreply.github.com"')
        os.system('git add history.json session.json')
        os.system('git commit -m "Auto-update session and history [skip ci]"')
        os.system('git push')
        print("تم حفظ الجلسة في GitHub بنجاح.")
    except Exception as e:
        print(f"Failed to commit to GitHub: {e}")

# --- تعديل الصورة تلقائياً (EXIF والقص) ---
def fix_and_crop_image(img_path):
    try:
        img = Image.open(img_path)
        # 1. تعديل الانقلاب التلقائي المخفي في إعدادات الكاميرا (EXIF)
        img = ImageOps.exif_transpose(img)
        
        # 2. التدوير التلقائي إذا كانت الصورة بالعرض
        if img.width > img.height:
            img = img.rotate(90, expand=True)
            
        # 3. قص الصورة بذكاء لتناسب مقاس الريلز 9:16
        target_ratio = 9 / 16
        img_ratio = img.width / img.height
        
        if img_ratio > target_ratio:
            new_width = int(target_ratio * img.height)
            offset = (img.width - new_width) / 2
            crop_box = (offset, 0, img.width - offset, img.height)
        else:
            new_height = int(img.width / target_ratio)
            offset = (img.height - new_height) / 2
            crop_box = (0, offset, img.width, img.height - offset)
            
        img = img.crop(crop_box)
        img = img.resize((1080, 1920), Image.Resampling.LANCZOS)
        img.save(img_path)
    except Exception as e:
        print(f"Error processing image {img_path}: {e}")

# --- دوال الذكاء الاصطناعي ---
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
    try:
        send_telegram_msg(f"⏳ جاري التواصل مع ذكاء Hugging Face لتحريك صورة معوز. قد يستغرق الأمر بعض الوقت...")
        client = GradioClient("stabilityai/stable-video-diffusion")
        # تم إزالة noise_aug_strength لحل مشكلة التحديث الجديد
        result = client.predict(
            image=handle_file(image_path),
            motion_bucket_id=127,      
            api_name="/video"
        )
        if result and os.path.exists(result):
            output_path = f"ai_video_{int(time.time())}_{random.randint(1,1000)}.mp4"
            shutil.copy(result, output_path)
            send_telegram_msg("✅ تم توليد فيديو الذكاء الاصطناعي بنجاح!")
            return output_path
    except Exception as e:
        send_telegram_msg(f"⚠️ تنبيه: سيرفر الذكاء الاصطناعي مشغول. سيتم استخدام التحريك البديل (MoviePy).\nالخطأ: {str(e)[:100]}")
    return None

# --- دوال المونتاج ---
def apply_ken_burns(image_path, duration=5):
    clip = ImageClip(image_path).set_duration(duration)
    clip = clip.resize(lambda t: 1 + 0.02 * t).set_position(('center', 'center'))
    return clip

def create_arabic_text_clip(text, size=(1080, 300), fontsize=140, font_path="taj.ttf"):
    if not os.path.exists(font_path):
        raise FileNotFoundError(f"ملف الخط '{font_path}' غير موجود في المشروع!")

    # إعدادات متقدمة لإجبار بايثون على ربط الحروف العربية
    configuration = {'delete_harakat': True, 'support_ligatures': True}
    reshaper = arabic_reshaper.ArabicReshaper(configuration=configuration)
    reshaped_text = reshaper.reshape(text)
    bidi_text = get_display(reshaped_text)
    
    img = Image.new('RGBA', size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(font_path, fontsize)
    
    text_bbox = draw.textbbox((0, 0), bidi_text, font=font)
    text_w = text_bbox[2] - text_bbox[0]
    text_h = text_bbox[3] - text_bbox[1]
    x = (size[0] - text_w) / 2
    y = (size[1] - text_h) / 2
    
    draw.text((x+5, y+5), bidi_text, font=font, fill=(0,0,0,200))
    draw.text((x, y), bidi_text, font=font, fill=(255,255,255,255))
    
    img_path = f"temp_text_{int(time.time())}.png"
    img.save(img_path)
    return ImageClip(img_path)

# --- المسار الرئيسي للعمل ---
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
        send_telegram_msg("⚠️ تنبيه أستاذ محمد: لا توجد صور جديدة كافية في المجلدات لصناعة فيديو اليوم.")
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

    for item in selected_images:
        fix_and_crop_image(item["path"])

    video_clips = []
    for item in selected_images:
        img_path = item["path"]
        type_name = item["type_name"]
        
        hf_vid_path = generate_video_hf(img_path, "")
        
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
        logo = ImageClip("logo.png").resize(height=250).margin(left=40, top=40, opacity=0).set_position(("left", "top")).set_duration(final_video.duration)
        final_video = CompositeVideoClip([final_video, logo])

    output_filename = f"bazheer_reel_{int(time.time())}.mp4"
    final_video.write_videofile(output_filename, fps=24, codec="libx264", audio_codec="aac")

    caption = generate_caption(list(set(types_used)))
    send_telegram_msg("⏳ جاري إرسال الفيديو المصنوع إلى تليجرام لمعاينته...")
    send_telegram_video(output_filename, f"🎥 الفيديو الجاهز للنشر\n\nالوصف:\n{caption}")

    # --- نظام إنستقرام الذكي المنيع ---
    cl = InstaClient()
    cl.delay_range = [2, 5] 
    
    session_file = "session.json"
    is_logged_in = False
    
    if os.path.exists(session_file):
        try:
            cl.load_settings(session_file)
            cl.get_timeline_feed()
            is_logged_in = True
        except Exception as e:
            send_telegram_msg("⚠️ الجلسة القديمة انتهت، جاري تسجيل دخول جديد...")
    
    if not is_logged_in:
        try:
            cl.login(IG_USERNAME, IG_PASSWORD)
            cl.dump_settings(session_file)
            commit_state_to_github() # حفظ الجلسة فوراً لضمان عدم ضياعها
            is_logged_in = True
        except Exception as e:
            error_str = str(e).lower()
            if "please wait" in error_str or "few minutes" in error_str:
                send_telegram_msg("⚠️ إنستقرام يطلب الانتظار. سيتم إيقاف المحاولة اليوم لتفادي الحظر النهائي.")
                # نخرج بسلام بدون خطأ أحمر عشان GitHub ما يزعل
                sys.exit(0) 
            elif "challenge" in error_str or "email" in error_str or "suspicious" in error_str:
                send_telegram_msg("⚠️ أستاذ محمد: إنستقرام يطلب التحقق (إيميل/تأكيد). افتح التطبيق ووافق. الكود ينتظر 3 دقائق...")
                time.sleep(180)
                cl.login(IG_USERNAME, IG_PASSWORD)
                cl.dump_settings(session_file)
                commit_state_to_github()
                is_logged_in = True
            else:
                send_telegram_msg(f"❌ خطأ غير متوقع في الدخول: {str(e)}")
                sys.exit(0)

    if is_logged_in:
        try:
            media = cl.clip_upload(output_filename, caption)
            save_history(history)
            commit_state_to_github() # حفظ السجل بعد النشر
            reel_url = f"https://www.instagram.com/reel/{media.code}/" if hasattr(media, 'code') else "تم النشر بنجاح."
            send_telegram_msg(f"✅ أهلاً أستاذ محمد، تم نشر مقطع اليوم بنجاح!\n\nالرابط:\n{reel_url}")
        except Exception as upload_error:
            send_telegram_msg(f"❌ خطأ أثناء النشر: {str(upload_error)}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        error_details = traceback.format_exc()
        send_telegram_msg(f"❌ خطأ برمجي:\n{str(e)}")
