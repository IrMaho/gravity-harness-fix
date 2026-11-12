# الدليل العربي الكامل — Gravity Harness Fix

**[English README](../README.md)** · **[فارسی](README.fa.md)** · **[تقرير التدقيق الإمبريقي (444 محادثة)](audit-all-conversations.md)**

---

## لماذا أنشأنا هذا المشروع؟

بعد تدقيق إحصائي لـ **444 سجلاً حقيقياً في Antigravity** (`16` محادثة رئيسية + `428` وكيلاً فرعياً بإجمالي **`106,004` خطوة**)، اتضح أن معظم البطء والأعطال يعود إلى اختناقات متكررة في البيئة وطريقة تشغيل الوكلاء:

- **`2,888` حلقة انتظار (`manage_task(status)`)** بدلاً من الانتظار التفاعلي.
- **`5,693` إعادة قراءة مكررة لنفس الملف** (`34%` من إجمالي عمليات القراءة).
- **`657` خطأً في علامات الاقتباس والأوامر متعددة الأسطر** بين PowerShell وPython/Node/WSL، و**`111` خطأ ترميز `cp1252`** على ويندوز.
- **`535` محاولة تعديل عشوائي (`edit_file`)** تتكرر دون إعادة قراءة الملف بعد الفشل.
- **هدر `400` خطوة مبدئية** داخل `/teamwork` التقليدي في المقابلات والتنسيق قبل كتابة سطر كود واحد، ثم تصادم `7` وكلاء داخل مجلد مشترك (`Workspace="inherit"`).
- تعثّر **`49.3%` من الوكلاء الفرعيين** بسبب ضغط API (`672.4` دقيقة انتظار).

يحوّل **`gravity-harness-fix`** كل هذه المشاكل إلى **حواجز برمجية فورية (`Hooks`)، وقواعد دائمة، ومهارة التوازي السريع `/agile-swarm`، وسجل مراقبة مستمر**.

---

## التثبيت بنقرة واحدة (لك ولأصدقائك)

1. استنسخ المستودع:
   ```sh
   git clone https://github.com/IrMaho/gravity-harness-fix.git
   ```
2. على **Windows**: انقر نقراً مزدوجاً على **`install.bat`**. سيقوم تلقائياً بـ:
   - اكتشاف جميع ملفات تعريف Antigravity (`%USERPROFILE%\.gemini` وأي بيئات معزولة)، وأخذ نسخة احتياطية.
   - تثبيت إضافة `gravity-harness-fix` (بما في ذلك المهارات العشر، حواجز الحماية، وخادم `gravity-memory` MCP) وتفعيلها داخل `config.json`.
   - تثبيت متغيرات `PYTHONIOENCODING=utf-8` و`PYTHONUTF8=1` على ويندوز، وإضافة `uv` إلى مسار WSL2.
   - تشغيل فحص عملي مباشر للحواجز (`Smoke Test`).
3. افتح **محادثة جديدة في Antigravity** (أو أعد تشغيل المحرر).

*(على macOS / Linux شغّل: `python3 scripts/install_harness.py`)*

---

## العمل المتوازي السريع على حساب واحد (`/agile-swarm` — Plan B)

بدلاً من `/teamwork` البطيء، ابدأ طلبك مباشرة بـ **`/agile-swarm`**:

```text
/agile-swarm أنشئ شاشات الملف الشخصي والمحفظة والإعدادات بشكل متوازٍ مع الاختبارات
```

### كيف يعمل `/agile-swarm`؟
1. **تقسيم فوري خلال أقل من دقيقتين (بلا مقابلات مملة):** يوزّع الوكيل الرئيسي العمل بين **`2` إلى `3` عمّال كحد أقصى** (الحد الآمن لحساب واحد لمنع أخطاء API) مع **ملكية ملفات غير متداخلة** وعقد واجهات واضح.
2. **عزل إجباري عبر `Workspace="share"`:** يمنع الـ Hook تشغيل وكلاء كتابة متوازين في `Workspace="inherit"` تلقائياً ويوجّههم لاستخدام `Workspace="share"` (بمثابة `git worktree` مدمج)، فينفّذ كل عامل فرعه `agile/<slice>` واختباراته السريعة ثم يودع التغييرات دون أي تعارض.
3. **نتيجة الاختبار العملي لبناء تطبيق Flutter من 10 شاشات (`PulseHub`):**
   - **الوقت الكلي من الصفر حتى الدمج واجتياز الاختبارات:** **`12.3` دقيقة**
   - **أزمنة العمّال الثلاثة المتوازين:** `4.38m` / `4.75m` / `5.95m`
   - **حجم الكود الحقيقي المكتوب:** **`5,804` سطر Dart** عبر `19` ملفاً
   - **تعارضات الدمج / حلقات الانتظار / تعثّر API:** **`0`** / **`0`** / **`0.0` دقيقة**
   - **الفحص النهائي:** `flutter analyze`: **0 مشاكل**، واجتياز **`11/11` اختباراً**.

---

## أداة `git worktree` المرفقة للاختبارات الثقيلة

لعزل اختبارات Docker/CI الطويلة أو العمل عبر نوافذ متوازية:

```bat
agile-worktree.bat create C:\path\to\repo slice-a slice-b wt-ci
agile-worktree.bat list C:\path\to\repo
agile-worktree.bat cleanup C:\path\to\repo --delete-branches
```

---

## حزمة أوامر السلاش الهندسية المتقدمة (`/pro-dev` Suite)

إلى جانب [`/agile-swarm`](../plugin/skills/agile-swarm/SKILL.md) و[`/gravity-session-doctor`](../plugin/skills/gravity-session-doctor/SKILL.md)، يضم المكون الإضافي **7 مهارات وأوامر سلاش احترافية** مع سكريبتات فحص بايثون حتمية (تُحمَّل عند الطلب فقط دون استهلاك السياق):

| الأمر | المهمة | أداة التحقق المرفقة |
|---|---|---|
| **`/pro-dev`** | المنسّق الرئيسي لدورة الهندسة الكاملة والتوجيه نحو التوازي عبر `/agile-swarm` | بوابات جودة موحدة وفصل الحقائق عن الاستنتاج |
| **`/repo-onboard`** | استكشاف المشاريع الجديدة وبناء ملف الذاكرة الحي `PROJECT_INTELLIGENCE.md` | فحص مسبق من 9 نقاط وبوابة قرار Option A/B |
| **`/forensic-audit`** | تدقيق جنائي معزول عبر `git worktree` في 14 مجالاً دون المساس بالكود الأصلي | مولّد تقرير HTML تفاعلي عبر [`generate_audit_report.py`](../plugin/skills/forensic-audit/scripts/generate_audit_report.py) |
| **`/harden-fix`** | تصنيف `Cat A/B/C` وإصلاح الجذور باختبارات مسبقة ومراجعة ثانية مستقلة | تتبّع القياسات قبل/بعد ومنع التراجعات |
| **`/lossless-modularize`** | تقسيم الملفات الضخمة إلى وحدات SOLID دون فقدان سطر أو رمز برمجي (`<= 400` سطر) | مدقق [`conservation_audit.py`](../plugin/skills/lossless-modularize/scripts/conservation_audit.py) |
| **`/figma-to-prod`** | تحويل Figma MCP إلى Flutter أو React+TS مع حفظ ملفات `.svg` الخام وحماية الحالات | مدقق [`verify_figma_ui.py`](../plugin/skills/figma-to-prod/scripts/verify_figma_ui.py) |
| **`/truthful-readme`** | بناء `README.md` موثّق بالبراهين ومخططات Mermaid ودليل ملاحة للوكلاء | مدقق [`verify_readme.py`](../plugin/skills/truthful-readme/scripts/verify_readme.py) |
| **`/memory-sync`** | ذاكرة دائمة ذكية من 5 طبقات (`L0`–`L4` + شظايا موضوعية + `SQLite FTS5` + فهرس AST + خادم MCP) | محرك [`memory_engine.py`](../plugin/skills/memory-sync/scripts/memory_engine.py) |

---

## معمارية الذاكرة الذكية ذات 5 طبقات وخادم `gravity-memory` MCP (`L0`–`L4`)

لتقليل استهلاك التوكنز الناتج عن إعادة قراءة الملفات الكبيرة ومنع فقدان السياق عند ضغط المحادثات الطويلة، يوفّر المشروع نظام ذاكرة مدمج بالمكتبة القياسية لـ Python (`SQLite WAL + FTS5`) مرتبطاً مباشرة بالحواجز وMCP:

- **`L0` الملفات الخام (قراءة بنطاق أسطر محدّد):** يمنع حاجز `PreToolUse` استدعاءات `read_file` غير المحدّدة بنطاق للملفات التي تتجاوز `260` سطراً و`2,500` بايت، ويوجه الوكيل إلى القراءة الموجّهة أو أداة [`symbol_lookup`](../plugin/mcp/memory_mcp_server.py).
- **`L1` خريطة الرموز (`TOON` + أولوية المعمارية):** تحديث تلقائي لقاعدة `.agents/memory/memory.db` عبر [`memory_indexer.py`](../plugin/skills/memory-sync/scripts/memory_indexer.py) مع ترجيح ملفات النواة فوق الاختبارات (`0.3x`) ودعم إخراج `format="toon"` المضغوط.
- **`L2` الفهرس المضغوط والدروس المتلاشية:** حقن `[L2 Memory]` مع تحذيرات `Avoid:` المستخرجة من [`memory_lesson`](../plugin/mcp/memory_mcp_server.py) (بنصف عمر `30` يوماً في `LESSONS.md`) تلقائياً عند `SessionStart`.
- **`L3` الشظايا الموضوعية (`<= 120` سطراً لكل ملف):** ملفات منظّمة داخل `.agents/memory/shards/` للبحث الفوري عبر `memory_search` (`FTS5` BM25 مع بديل `LIKE`).
- **`L4` نقاط الحفظ والاسترجاع (`memory_checkpoint`):** حفظ مخرجات الجلسة والخطوة التالية مع تنبيه استباقي كل `150` خطوة، وضبط [`mcp_config.json`](../plugin/mcp_config.json) بمسارات مطلقة عبر المثبّت.

---

## المراقبة المستمرة والتحسين (`gravity-session-doctor`)

- تسجّل الإضافة تلقائياً أي أخطاء جديدة أو محاولات محجوبة داخل **`logs/session-issues.jsonl`** وملف الملخص **`logs/latest-summary.md`** (مستثناة في `.gitignore` لحماية خصوصيتك).
- انقر نقراً مزدوجاً على **`audit_all_conversations.bat`** أو اطلب من الوكيل مراجعة السجلات لإضافة قواعد واختبارات جديدة.
- للإزالة الكاملة استخدم **`uninstall.bat`**.

