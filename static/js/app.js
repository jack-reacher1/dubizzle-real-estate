(() => {
  'use strict';

const PAGE_SIZE = 20;

const state = {
  loading: false,
  loadingMore: false,
  compoundsTimer: null,
  lastError: null,
  filtersOpen: false,
  currentResults: [],
  currentPage: 1,
  totalPages: 1,
  totalResults: 0
};

  const $ = (id) => document.getElementById(id);

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function number(value) {
    if (value === null || value === undefined || value === '') {
      return null;
    }

    const parsed = Number(value);

    return Number.isFinite(parsed) ? parsed : null;
  }

  function formatPrice(value) {
    const n = number(value);

    if (n === null) {
      return 'السعر غير متاح';
    }

    return `${n.toLocaleString('ar-EG')} جنيه`;
  }

  function formatNumber(value) {
    const n = number(value);

    return n === null
      ? 'غير متاح'
      : n.toLocaleString('ar-EG');
  }

  // Active-ads count must render as a plain digit (0, 1, 2, ...)
  // or "غير متاح". Never convert unknown/null into 0.
  function formatActiveCount(value) {
    const n = number(value);

    if (n === null) {
      return 'غير متاح';
    }

    return String(n);
  }

  function formatFreshness(days, updatedAt) {
    const direct = number(days);

    if (direct !== null) {
      if (direct <= 0) return 'اليوم';
      if (direct === 1) return 'منذ يوم';

      return `منذ ${Math.floor(direct)} أيام`;
    }

    if (!updatedAt) {
      return '';
    }

    const timestamp = new Date(updatedAt).getTime();

    if (!Number.isFinite(timestamp)) {
      return '';
    }

    const diff = Math.max(
      0,
      Math.floor((Date.now() - timestamp) / 86400000)
    );

    if (diff === 0) return 'اليوم';
    if (diff === 1) return 'منذ يوم';

    return `منذ ${diff} أيام`;
  }

  function normalizeResponse(payload) {
    if (Array.isArray(payload)) {
      return {
        results: payload,
        total: payload.length,
        page: 1,
        perPage: payload.length,
        totalPages: 1
      };
    }

    if (!payload || typeof payload !== 'object') {
      throw new Error('Unexpected API response shape');
    }

    const results =
      Array.isArray(payload.results)
        ? payload.results
        : Array.isArray(payload.items)
          ? payload.items
          : Array.isArray(payload.listings)
            ? payload.listings
            : [];

    const total = number(payload.total) ?? results.length;
    const page = number(payload.page) ?? 1;
    const perPage = number(payload.per_page) ?? PAGE_SIZE;
    const totalPages =
      number(payload.total_pages) ??
      Math.max(1, Math.ceil(total / Math.max(perPage, 1)));

    return {
      results,
      total,
      page,
      perPage,
      totalPages
    };
  }

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: {
        Accept: 'application/json',
        ...(options.headers || {})
      }
    });

    const text = await response.text();

    let payload = null;

    try {
      payload = text ? JSON.parse(text) : null;
    } catch {
      payload = null;
    }

    if (!response.ok) {
      const detail =
        payload?.detail ||
        payload?.message ||
        `HTTP ${response.status}`;

      throw new Error(detail);
    }

    if (payload === null) {
      throw new Error('الخادم رجّع استجابة غير صالحة');
    }

    return payload;
  }

  function selectedListingType() {
    return (
      document.querySelector(
        'input[name="listing_type_ui"]:checked'
      )?.value || ''
    );
  }

  function selectedLeadStatus() {
    return document.querySelector(
      'input[name="lead_status_ui"]:checked'
    )?.value || '';
  }

  function buildParams(page = 1) {
    const params = new URLSearchParams();

    const values = {
      listing_type: selectedListingType(),
      lead_status: selectedLeadStatus(),
      property_type: $('property_type')?.value || '',
      compound: $('compound')?.value?.trim() || '',
      min_price: $('min_price')?.value || '',
      max_price: $('max_price')?.value || '',
      min_area: $('min_area')?.value || '',
      max_area: $('max_area')?.value || '',
      bedrooms_min: $('bedrooms_min')?.value || '',
      bathrooms_min: $('bathrooms_min')?.value || '',
      completion_status: $('completion_status')?.value || '',
      freshness: $('freshness')?.value || '',
      sort: $('sort')?.value || 'newest',
      q: $('smart-search')?.value?.trim() || ''
    };

    Object.entries(values).forEach(([key, value]) => {
      if (value !== '') {
        params.set(key, value);
      }
    });

    params.set('page', String(page));
    params.set('per_page', String(PAGE_SIZE));

    return params;
  }

  function showLoading() {
    $('listings').innerHTML = `
      <div class="loading-state">
        <div class="spinner" aria-hidden="true"></div>
        <p>بنجيب أحدث الفرص المتاحة...</p>
      </div>
    `;

    $('results-summary').textContent = 'جاري التحديث...';
  }

  function showError(error) {
    state.lastError = error;

    $('listings').innerHTML = `
      <div class="state-panel error-state">
        <div class="state-icon" aria-hidden="true">!</div>

        <h3>مش قادرين نحمل الإعلانات دلوقتي</h3>

        <p>
          حصلت مشكلة أثناء الاتصال بالبيانات.
          جرّب مرة تانية بدون تغيير الفلاتر.
        </p>

        <button
          id="retry-load"
          class="btn btn-primary"
          type="button"
        >
          إعادة المحاولة
        </button>
      </div>
    `;

    $('results-summary').textContent = 'تعذر تحميل النتائج';
    $('result-count').textContent = 'تعذر التحميل';

    console.error(
      '[UI] Failed to load listings:',
      error
    );
  }

  function renderEmpty() {
    $('listings').innerHTML = `
      <div class="state-panel empty-state">
        <div class="state-icon" aria-hidden="true">⌕</div>

        <h3>مفيش إعلانات مطابقة دلوقتي</h3>

        <p>
          وسّع البحث أو امسح بعض الفلاتر علشان تشوف فرص أكتر.
        </p>

        <button
          id="reset-from-empty"
          class="btn btn-ghost"
          type="button"
        >
          مسح الفلاتر
        </button>
      </div>
    `;
  }

  function formatScrapeTimestamp(value) {
    if (!value) {
      return 'غير متاح';
    }

    const timestamp = new Date(value);

    if (Number.isNaN(timestamp.getTime())) {
      return 'غير متاح';
    }

    return new Intl.DateTimeFormat('ar-EG', {
      dateStyle: 'medium',
      timeStyle: 'short',
      timeZone: 'UTC'
    }).format(timestamp);
  }

  function renderScrapeStatus(meta) {
    const statusEl = $('scrape-status');

    if (!statusEl) {
      return;
    }

    statusEl.textContent = `آخر scrape: ${formatScrapeTimestamp(meta?.last_successful_scrape_at)}`;
  }

  async function fetchMeta() {
    try {
      const payload = await fetchJson('/api/meta');
      renderScrapeStatus(payload);
    } catch (error) {
      console.warn('[UI] Failed to load scrape metadata:', error);
      renderScrapeStatus(null);
    }
  }

  function metaItem(icon, label, value) {
    if (
      value === null ||
      value === undefined ||
      value === ''
    ) {
      return '';
    }

    return `
      <span class="meta-item">
        <span class="meta-icon" aria-hidden="true">${icon}</span>
        <span>
          ${escapeHtml(value)}
          ${escapeHtml(label)}
        </span>
      </span>
    `;
  }

  function renderCard(listing, index) {
    const title = escapeHtml(
      listing.title || 'إعلان عقاري'
    );

    const compound = escapeHtml(
      listing.compound ||
      listing.location_text ||
      'الموقع غير متاح'
    );

    const freshness = escapeHtml(
      formatFreshness(
        listing.days_since_updated,
        listing.updated_at
      )
    );

    const price = escapeHtml(
      formatPrice(listing.price)
    );

    const description = escapeHtml(
      listing.description_full ||
      'لا يوجد وصف متاح.'
    );

    const seller = escapeHtml(
      listing.seller_name ||
      'اسم البائع غير متاح'
    );

    const activeAds = number(
      listing.active_ads_count
    );

    return `
      <article
        class="listing-card"
        data-index="${index}"
      >
        <div class="listing-card-top">
          <div class="listing-primary">
            <div class="listing-badges">
              ${
                listing.likely_owner
                  ? '<span class="badge owner-badge">مالك مرجح</span>'
                  : ''
              }

              ${
                freshness
                  ? `<span class="badge freshness-badge">${freshness}</span>`
                  : ''
              }

              ${
                listing.listing_type
                  ? `<span class="badge type-badge">${
                      listing.listing_type === 'rent'
                        ? 'إيجار'
                        : 'بيع'
                    }</span>`
                  : ''
              }

              <span class="badge lead-status-badge ${
                listing.lead_status === 'contacted'
                  ? 'contacted'
                  : 'new'
              }">
                ${listing.lead_status === 'contacted' ? 'تم التواصل' : 'لسه ما اتواصلتش'}
              </span>
            </div>

            <h3 class="listing-title">
              ${title}
            </h3>

            <p class="listing-location">
              ${compound}
            </p>
          </div>

          <div class="price-block">
            <span class="price-label">السعر</span>

            <strong>
              ${price}
            </strong>
          </div>
        </div>

        <div class="listing-meta">
          ${metaItem('⌂', 'م²', listing.area_sqm)}
          ${metaItem('◈', 'غرف', listing.bedrooms)}
          ${metaItem('♧', 'حمام', listing.bathrooms)}
          ${metaItem('●', '', listing.property_type)}
        </div>

        <div class="seller-row">
          <div class="seller-info">
            <span class="seller-label">
              البائع
            </span>

            <strong>
              ${seller}
            </strong>
          </div>

          <div class="seller-count">
            <span class="seller-label">
              الإعلانات النشطة
            </span>

            <strong>
              ${
                activeAds === null
                  ? 'غير متاح'
                  : formatActiveCount(activeAds)
              }
            </strong>
          </div>
        </div>

        <div class="description-wrap">
          <p class="listing-description">
            ${description}
          </p>

          ${
            listing.description_full
              ? '<button class="link-button toggle-description" type="button">عرض الوصف كاملًا</button>'
              : ''
          }
        </div>

        <div class="card-actions">
          <button
            class="btn btn-contact ${listing.lead_status === 'contacted' ? 'btn-contacted' : 'btn-primary'}"
            type="button"
            data-ad-id="${escapeHtml(listing.ad_id)}"
            ${listing.lead_status === 'contacted' ? 'disabled' : ''}
          >
            ${listing.lead_status === 'contacted' ? 'تم التواصل' : 'تواصلت معاه'}
          </button>

          <button
            class="btn btn-ghost btn-details"
            type="button"
          >
            تفاصيل الإعلان
          </button>

          ${
            listing.ad_url
              ? `
                <a
                  class="btn btn-primary btn-open"
                  target="_blank"
                  rel="noopener noreferrer"
                  href="${escapeHtml(listing.ad_url)}"
                >
                  فتح الإعلان
                </a>
              `
              : `
                <span
                  class="btn btn-disabled"
                  aria-disabled="true"
                >
                  الرابط غير متاح
                </span>
              `
          }
        </div>
      </article>
    `;
  }

  function renderResults(results, total, page, totalPages, append = false) {
    if (append) {
      state.currentResults = [
        ...state.currentResults,
        ...results
      ];
    } else {
      state.currentResults = results;
    }

    state.currentPage = page;
    state.totalPages = totalPages;
    state.totalResults = total;

    $('result-count').textContent =
      `${formatNumber(total)} إعلان`;

    const shownCount = state.currentResults.length;

    $('results-summary').textContent =
      shownCount >= total
        ? `${formatNumber(total)} نتيجة`
        : `عرض ${formatNumber(shownCount)} من ${formatNumber(total)}`;

    if (!state.currentResults.length) {
      renderEmpty();
      return;
    }

    const cardsHtml = state.currentResults
      .map((listing, index) => renderCard(listing, index))
      .join('');

    const canLoadMore =
      state.currentPage < state.totalPages;

    const loadMoreHtml = canLoadMore
      ? `
        <div class="load-more-wrap">
          <button
            id="load-more"
            class="btn btn-primary load-more-btn"
            type="button"
          >
            عرض المزيد
          </button>

          <span class="load-more-hint">
            عرض ${formatNumber(shownCount)} من ${formatNumber(total)}
          </span>
        </div>
      `
      : `
        <div class="load-more-wrap load-more-end">
          <span class="load-more-hint">
            تم عرض كل الإعلانات المتاحة
          </span>
        </div>
      `;

    $('listings').innerHTML =
      cardsHtml + loadMoreHtml;

    updateActiveFilters();
  }

  async function loadAndRender({ append = false } = {}) {
    if (state.loading || state.loadingMore) {
      return;
    }

    const page = append
      ? state.currentPage + 1
      : 1;

    if (append && page > state.totalPages) {
      return;
    }

    if (append) {
      state.loadingMore = true;

      const button = $('load-more');

      if (button) {
        button.disabled = true;
        button.textContent = 'جاري تحميل المزيد...';
      }
    } else {
      state.loading = true;
      showLoading();
    }

    try {
      const params = buildParams(page);

      const payload = await fetchJson(
        `/api/listings?${params.toString()}`
      );

      const normalized =
        normalizeResponse(payload);

      renderResults(
        normalized.results,
        normalized.total,
        normalized.page,
        normalized.totalPages,
        append
      );
    } catch (error) {
      if (append) {
        const button = $('load-more');

        if (button) {
          button.disabled = false;
          button.textContent = 'عرض المزيد';
        }

        console.error(
          '[UI] Failed to load more listings:',
          error
        );
      } else {
        showError(error);
      }
    } finally {
      state.loading = false;
      state.loadingMore = false;
    }
  }

  async function markContacted(adId, button) {
    button.disabled = true;
    try {
      await fetchJson(`/api/listings/${encodeURIComponent(adId)}/lead-status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'contacted' })
      });
      const listing = state.currentResults.find((item) => item.ad_id === adId);
      if (listing) {
        listing.lead_status = 'contacted';
        renderResults(state.currentResults, state.totalResults, state.currentPage, state.totalPages);
      }
    } catch (error) {
      button.disabled = false;
      console.error('[UI] Failed to update lead status:', error);
    }
  }

  async function fetchCompounds(query = '') {
    const payload = await fetchJson(
      `/api/compounds?q=${encodeURIComponent(query)}`
    );

    if (Array.isArray(payload)) {
      return payload;
    }

    if (Array.isArray(payload.results)) {
      return payload.results;
    }

    if (Array.isArray(payload.items)) {
      return payload.items;
    }

    if (Array.isArray(payload.compounds)) {
      return payload.compounds;
    }

    return [];
  }

  async function updateCompoundOptions(query) {
    try {
      const values = await fetchCompounds(query);
      const list = $('compound-list');

      list.innerHTML = '';

      values
        .slice(0, 30)
        .forEach((value) => {
          const option =
            document.createElement('option');

          option.value = value;

          list.appendChild(option);
        });
    } catch (error) {
      console.warn(
        '[UI] Compound autocomplete failed:',
        error
      );
    }
  }

  function openFilters() {
    const panel = $('filters-panel');

    panel.classList.add('is-open');
    panel.setAttribute(
      'aria-hidden',
      'false'
    );

    document.body.classList.add(
      'filters-open'
    );

    state.filtersOpen = true;
  }

  function closeFilters() {
    const panel = $('filters-panel');

    panel.classList.remove('is-open');
    panel.setAttribute(
      'aria-hidden',
      'true'
    );

    document.body.classList.remove(
      'filters-open'
    );

    state.filtersOpen = false;
  }

  function resetFilters() {
    document
      .querySelectorAll(
        '#filters-panel input, #filters-panel select'
      )
      .forEach((field) => {
        field.value = '';
      });

    const allListingType =
      document.querySelector(
        'input[name="listing_type_ui"][value=""]'
      );

    if (allListingType) {
      allListingType.checked = true;
    }

    const allLeadStatus = document.querySelector(
      'input[name="lead_status_ui"][value=""]'
    );

    if (allLeadStatus) {
      allLeadStatus.checked = true;
    }

    $('sort').value = 'newest';
    $('smart-search').value = '';
    $('clear-search').classList.add('hidden');

    updateActiveFilters();

    closeFilters();

    loadAndRender();
  }

  function updateActiveFilters() {
    const container = $('active-filters');
    const chips = [];

    const values = [
      [
        'بيع',
        selectedListingType() === 'sale'
      ],
      [
        'إيجار',
        selectedListingType() === 'rent'
      ],
      [
        $('property_type')?.selectedOptions[0]?.textContent,
        !!$('property_type')?.value
      ],
      [
        $('compound')?.value,
        !!$('compound')?.value
      ],
      [
        `من ${$('min_price')?.value}`,
        !!$('min_price')?.value
      ],
      [
        `إلى ${$('max_price')?.value}`,
        !!$('max_price')?.value
      ],
      [
        `${$('bedrooms_min')?.value}+ غرف`,
        !!$('bedrooms_min')?.value
      ],
      [
        `${$('bathrooms_min')?.value}+ حمام`,
        !!$('bathrooms_min')?.value
      ],
      [
        $('freshness')?.selectedOptions[0]?.textContent,
        !!$('freshness')?.value
      ],
      [
        $('smart-search')?.value,
        !!$('smart-search')?.value
      ]
    ];

    values.forEach(
      ([label, active]) => {
        if (active && label) {
          chips.push(
            `<span class="filter-chip">${escapeHtml(label)}</span>`
          );
        }
      }
    );

    container.innerHTML =
      chips.length
        ? `
          <span class="filter-chip-label">
            الفلاتر الحالية
          </span>
          ${chips.join('')}
        `
        : '';
  }

  async function openListingDetails(index) {
    const listing =
      state.currentResults[index];

    if (!listing) {
      return;
    }

    const dialog = $('listing-dialog');
    const content = $('dialog-content');

    content.innerHTML = `
      <span class="section-kicker">
        تفاصيل الإعلان
      </span>

      <h2>
        ${escapeHtml(
          listing.title || 'إعلان عقاري'
        )}
      </h2>

      <div class="dialog-price">
        ${escapeHtml(
          formatPrice(listing.price)
        )}
      </div>

      <div class="dialog-grid">
        ${metaItem('⌂', 'م²', listing.area_sqm)}
        ${metaItem('◈', 'غرف', listing.bedrooms)}
        ${metaItem('♧', 'حمام', listing.bathrooms)}
        ${metaItem('●', '', listing.property_type)}
      </div>

      <div class="dialog-section">
        <span class="section-kicker">
          الموقع
        </span>

        <p>
          ${escapeHtml(
            listing.compound ||
            listing.location_text ||
            'غير متاح'
          )}
        </p>
      </div>

      <div class="dialog-section">
        <span class="section-kicker">
          البائع
        </span>

        <p>
          <strong>
            ${escapeHtml(
              listing.seller_name ||
              'غير متاح'
            )}
          </strong>
        </p>

        <p>
          الإعلانات النشطة:
          ${
            number(listing.active_ads_count) === null
              ? 'غير متاح'
              : formatActiveCount(
                  listing.active_ads_count
                )
          }
        </p>

        ${
          listing.likely_owner
            ? '<span class="badge owner-badge">مالك مرجح</span>'
            : ''
        }
      </div>

      <div class="dialog-section">
        <span class="section-kicker">
          الوصف الكامل
        </span>

        <p class="dialog-description">
          ${escapeHtml(
            listing.description_full ||
            'لا يوجد وصف متاح.'
          )}
        </p>
      </div>

      <div class="dialog-actions">
        ${
          listing.ad_url
            ? `
              <a
                class="btn btn-primary"
                target="_blank"
                rel="noopener noreferrer"
                href="${escapeHtml(listing.ad_url)}"
              >
                فتح الإعلان الأصلي
              </a>
            `
            : `
              <span
                class="btn btn-disabled"
                aria-disabled="true"
              >
                الرابط غير متاح
              </span>
            `
        }
      </div>
    `;

    if (
      typeof dialog.showModal === 'function'
    ) {
      dialog.showModal();
    } else {
      dialog.setAttribute('open', '');
    }
  }

  function bindEvents() {
    $('open-filters')
      .addEventListener(
        'click',
        openFilters
      );

    $('close-filters')
      .addEventListener(
        'click',
        closeFilters
      );

    $('filters-backdrop')
      .addEventListener(
        'click',
        closeFilters
      );

    $('apply-filters')
      .addEventListener(
        'click',
        () => {
          closeFilters();
          loadAndRender();
        }
      );

    $('reset-filters')
      .addEventListener(
        'click',
        resetFilters
      );

    $('search-btn')
      .addEventListener(
        'click',
        loadAndRender
      );

    $('sort')
      .addEventListener(
        'change',
        () => {
          updateActiveFilters();
          loadAndRender();
        }
      );

    $('smart-search')
      .addEventListener(
        'input',
        () => {
          $('clear-search')
            .classList.toggle(
              'hidden',
              !$('smart-search').value
            );

          updateActiveFilters();
        }
      );

    $('clear-search')
      .addEventListener(
        'click',
        () => {
          $('smart-search').value = '';

          $('clear-search')
            .classList.add('hidden');

          loadAndRender();
        }
      );

    $('smart-search')
      .addEventListener(
        'keydown',
        (event) => {
          if (event.key === 'Enter') {
            loadAndRender();
          }
        }
      );

    /*
     * Transaction type:
     * Apply immediately when the user selects
     * بيع / إيجار / الكل.
     */
    document
      .querySelectorAll(
        'input[name="listing_type_ui"]'
      )
      .forEach((input) => {
        input.addEventListener(
          'change',
          () => {
            updateActiveFilters();
            loadAndRender();
          }
        );
      });

    document
      .querySelectorAll('input[name="lead_status_ui"]')
      .forEach((input) => {
        input.addEventListener('change', () => {
          updateActiveFilters();
          loadAndRender();
        });
      });

    /*
     * Discrete filters:
     * Apply immediately because the user chooses
     * a complete value rather than typing a range.
     */
    [
      'property_type',
      'bedrooms_min',
      'bathrooms_min',
      'completion_status',
      'freshness'
    ].forEach((id) => {
      const field = $(id);

      if (!field) {
        return;
      }

      field.addEventListener(
        'change',
        () => {
          updateActiveFilters();
          loadAndRender();
        }
      );
    });

    /*
     * Numeric range fields intentionally do NOT auto-query
     * on every keystroke.
     *
     * The user can enter both values and then press
     * "عرض النتائج".
     */
    [
      'min_price',
      'max_price',
      'min_area',
      'max_area'
    ].forEach((id) => {
      const field = $(id);

      if (!field) {
        return;
      }

      field.addEventListener(
        'input',
        updateActiveFilters
      );

      field.addEventListener(
        'keydown',
        (event) => {
          if (event.key === 'Enter') {
            loadAndRender();
          }
        }
      );
    });

    /*
     * Compound:
     * Autocomplete updates as the user types.
     * The actual listing filter is applied when the
     * user chooses a compound or presses Enter.
     */
    $('compound')
      .addEventListener(
        'input',
        () => {
          clearTimeout(
            state.compoundsTimer
          );

          state.compoundsTimer =
            setTimeout(
              () =>
                updateCompoundOptions(
                  $('compound').value.trim()
                ),
              220
            );

          updateActiveFilters();
        }
      );

    $('compound')
      .addEventListener(
        'change',
        () => {
          updateActiveFilters();
          loadAndRender();
        }
      );

    $('compound')
      .addEventListener(
        'keydown',
        (event) => {
          if (event.key === 'Enter') {
            loadAndRender();
          }
        }
      );

    document
      .querySelectorAll(
        '#filters-panel select'
      )
      .forEach((field) => {
        field.addEventListener(
          'change',
          updateActiveFilters
        );
      });

    $('listings')
      .addEventListener(
        'click',
        (event) => {
            const loadMore =
            event.target.closest('#load-more');

          if (loadMore) {
            loadAndRender({
              append: true
            });
            return;
          }

          const contactButton = event.target.closest('.btn-contact');
          if (contactButton && !contactButton.disabled) {
            markContacted(contactButton.dataset.adId, contactButton);
            return;
          }
          const retry =
            event.target.closest(
              '#retry-load'
            );

          if (retry) {
            loadAndRender();
          }

          const reset =
            event.target.closest(
              '#reset-from-empty'
            );

          if (reset) {
            resetFilters();
          }

          const descriptionButton =
            event.target.closest(
              '.toggle-description'
            );

          if (descriptionButton) {
            const card =
              descriptionButton.closest(
                '.listing-card'
              );

            card?.classList.toggle(
              'description-expanded'
            );

            descriptionButton.textContent =
              card?.classList.contains(
                'description-expanded'
              )
                ? 'إخفاء جزء من الوصف'
                : 'عرض الوصف كاملًا';
          }

          const details =
            event.target.closest(
              '.btn-details'
            );

          if (details) {
            const card =
              details.closest(
                '.listing-card'
              );

            if (card) {
              openListingDetails(
                Number(card.dataset.index)
              );
            }
          }
        }
      );

    $('close-dialog')
      .addEventListener(
        'click',
        () => {
          $('listing-dialog').close();
        }
      );

    $('listing-dialog')
      .addEventListener(
        'click',
        (event) => {
          if (
            event.target ===
            $('listing-dialog')
          ) {
            $('listing-dialog').close();
          }
        }
      );

    window.addEventListener(
      'resize',
      () => {
        if (
          window.innerWidth > 980 &&
          state.filtersOpen
        ) {
          closeFilters();
        }
      }
    );
  }

  document.addEventListener(
    'DOMContentLoaded',
    () => {
      bindEvents();
      updateActiveFilters();
      fetchMeta();
      loadAndRender();
    }
  );
})();