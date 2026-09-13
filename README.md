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

## PostgreSQL وVercel وWorker

1. أنشئ قاعدة PostgreSQL واضبط `DATABASE_URL` و`STORAGE_BACKEND=postgres`.
2. نفّذ `scripts/002_create_postgres_schema.sql` مرة واحدة.
3. لترحيل البيانات الحالية، شغّل `python scripts/migrate_csv_to_postgres.py`.
4. انشر `worker/Dockerfile` كـ Render Web Service باستخدام `render.yaml`.
5. اضبط في Render `DATABASE_URL` و`WORKER_TRIGGER_SECRET` و`STORAGE_BACKEND=postgres`.
6. اضبط في Vercel `WORKER_URL` و`WORKER_TRIGGER_SECRET` و`CRON_SECRET`.
7. اربط المستودع بـ Vercel وانشره. `vercel.json` يضيف Vercel Cron في نفس مواعيد التشغيل السابقة.

نقطة الدخول هي `vercel_api_index.py`. واجهات `/api/listings` و`/api/compounds`
و`/api/listing/{ad_id}` تقرأ من view `business_listings` عند تشغيل PostgreSQL.
نقطة `/api/cron/scrape` تتطلب `Authorization: Bearer <CRON_SECRET>`، وتطلب
تشغيلًا سريعًا من Worker على Render. الـ Worker نفسه يستخدم PostgreSQL advisory lock
لمنع تشغيلين متزامنين ثم يشغل `scraper.py` خارج Vercel.

للاختبار اليدوي:

```bash
curl -X POST https://YOUR_DOMAIN/api/cron/scrape \
   -H "Authorization: Bearer YOUR_CRON_SECRET"
```

للاختبار المباشر للـ Worker:

```bash
curl https://YOUR_WORKER_DOMAIN/health
curl -X POST https://YOUR_WORKER_DOMAIN/run \
   -H "Authorization: Bearer YOUR_WORKER_TRIGGER_SECRET"
```

يستجيب الـ Worker بسرعة بحالة `accepted`، ثم يكمل الـ scrape في الخلفية.

### Environment variables

يجب أن تكون `DATABASE_URL` و`STORAGE_BACKEND=postgres` و`WORKER_TRIGGER_SECRET`
موجودة في Render. يجب أن تكون `WORKER_URL` و`WORKER_TRIGGER_SECRET` و`CRON_SECRET`
موجودة في Vercel. بقية إعدادات Dubizzle الحالية يمكن نقلها إلى Render كما هي،
بما فيها `DUBIZZLE_MAX_PAGES` و`DUBIZZLE_MAX_RETRIES` و`DUBIZZLE_REQUEST_TIMEOUT_SECONDS`
والـ delay settings.

## GitHub

GitHub يبقى للمصدر وCI/CD فقط. تم حذف workflows الخاصة بالتشغيل المجدول؛
الجدولة والتنفيذ الإنتاجي يتمان من Vercel Cron.
