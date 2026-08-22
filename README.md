# dubizzle-real-estate

# Dubizzle Egypt - 5th Settlement Scraper

سكريبر يومي بيسحب إعلانات الشقق (بيع وإيجار) في التجمع الخامس من Dubizzle مصر،
بيطبق فلاتر لاستبعاد السماسرة/الشركات ويولّد ملف بيانات مخصّص للمطور العقاري.
الواجهة البسيطة تعرض "إعلانات ملاك مرجّح" فقط، مع رابط للإعلان الأصلي على Dubizzle.

الشرح هنا مُركّز بالعربية لأنّ المستخدم النهائي هو مطوّر عقاري عربي.

## ملاحظات مهمة قبل التشغيل

1. افتح `view-source:` لصفحة بحث حقيقية (زي رابط `sale` في `SEARCH_URLS` جوه `scraper.py`)،
   ودور على `<script id="__NEXT_DATA__">`. لو موجود، طبع محتواه بصيغة JSON وشوف مسار
   الليستنجز الحقيقي جوه الشجرة — ممكن تختلف الأسماء عن المفترض في `parse_search_results_from_next_data`.

2. لو `__NEXT_DATA__` مش موجود خالص، الموقع مش شغال بـ Next.js وهتحتاج تبني parser بديل
   باستخدام CSS selectors بعد ما تفتح Inspect Element على صفحة حقيقية.

نفس الكلام على صفحة البروفايل بتاعة البائع (`check_seller_profile`) — لازم تتأكد من شكل
الرابط الحقيقي ومكان `activeAdsCount` جوه الداتا.

## التشغيل محلياً

```bash
pip install -r requirements.txt
python scraper.py
```

هيطلع لك ملفات جوا `data/`:
- `listings.csv`: كل الإعلانات المتراكمة
- `sellers_cache.csv`: كاش تصنيف البائعين (مالك/سمسار)
- `business_listings.csv`: مجموعة الإعلانات المؤهلة كـ leads

## الجدولة الآلية

`.github/workflows/daily_scrape.yml` بيشغل السكريبر كل يوم الساعة 12 ظهراً بتوقيت القاهرة،
وبيعمل commit للملفين رجوع للريبو تلقائياً (تأكد من صلاحيات contents: write في الـ workflow).

## الخطوات الجاية

- Phase 2: ملف تفاعلي بفلاتر فوق `listings.csv`
- Phase 3: بوت تليجرام للتنبيهات
- ترحيل بيانات إلى Postgres (اختياري) لعمل DB-backed API ووقف الاعتماد على commits للتحديث
