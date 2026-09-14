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

بدون `STORAGE_BACKEND=postgres` يستمر التشغيل المحلي والاختبارات باستخدام ملفات CSV.
في الإنتاج لا تعتمد Vercel على هذه الملفات؛ PostgreSQL هو مصدر الحقيقة.

## PostgreSQL وVercel وGitHub Actions

1. أنشئ قاعدة PostgreSQL واضبط `DATABASE_URL` و`STORAGE_BACKEND=postgres`.
2. نفّذ `scripts/002_create_postgres_schema.sql` مرة واحدة.
3. لترحيل البيانات الحالية، شغّل `python scripts/migrate_csv_to_postgres.py`.
4. اربط المستودع بـ Vercel وانشر نقطة الدخول `vercel_api_index.py`.
5. احتفظ بملف `vercel.json` ليختار نقطة الدخول والـ routes الصحيحة في Vercel.
6. اجعل التشغيل المجدول تابعًا فقط لـ GitHub Actions عبر `.github/workflows/scrape.yml`.

نقطة الدخول هي `vercel_api_index.py`. واجهات `/api/listings` و`/api/compounds`
و`/api/listing/{ad_id}` تقرأ من view `business_listings` عند تشغيل PostgreSQL.
لا توجد نقطة `/api/cron/scrape` داخل التطبيق، لأنّ الجلب المجدول يتم مباشرة من
GitHub Actions داخل نفس ال job الذي يركّب البيئة ويشغّل `scripts/run_scrape_with_tracking.py`.

### Environment variables

يجب أن تكون `DATABASE_URL` و`STORAGE_BACKEND=postgres` موجودة في GitHub Secrets
وأن تهيّئها في job الخاص بـ `.github/workflows/scrape.yml`. بقية إعدادات Dubizzle
الحالية تذهب عبر env في نفس workflow، بما فيها `DUBIZZLE_MAX_PAGES` و
`DUBIZZLE_MAX_RETRIES` و`DUBIZZLE_REQUEST_TIMEOUT_SECONDS` والـ delay settings.

## GitHub

GitHub يبقى للمصدر وCI/CD فقط. الـ workflow المجدول في `.github/workflows/scrape.yml`
يستخدم توقيتًا من اليوم 1 إلى اليوم 7، ثلاث مرات يوميًا عند 00:00 و08:00 و16:00 UTC.
يسمح هذا بالتشغيل الموحّد عبر GitHub Actions دون الاعتماد على Vercel Cron أو Render.
