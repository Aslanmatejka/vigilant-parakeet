import React from 'react';
import { toast } from 'react-toastify';
import dataService from '../../utils/dataService';
import supabase from '../../utils/supabaseClient';

const CATEGORIES = [
  'produce',
  'bakery',
  'dairy',
  'pantry',
  'meat',
  'prepared',
  'seafood',
  'frozen',
  'snacks',
  'beverages',
  'other',
];
const URGENCY = ['low', 'normal', 'high', 'urgent'];
const LISTING_TYPES = ['donation', 'request'];
const STORAGE_REQUIREMENTS = ['refrigerated', 'frozen', 'room_temperature', 'cool_dry', 'heated'];
const PACKAGING_TYPES = [
  'sealed_original',
  'sealed_container',
  'wrapped',
  'open_container',
  'unwrapped',
  'vacuum_sealed',
];
const CONDITIONS = ['excellent', 'good', 'fair', 'poor', 'unsafe'];

function formatDate(dateString) {
  if (!dateString) return null;
  try {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  } catch {
    return String(dateString);
  }
}

function formatDateOnly(dateString) {
  if (!dateString) return null;
  const raw = String(dateString).slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) return formatDate(dateString);
  const [y, m, d] = raw.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function asList(value) {
  if (!value) return [];
  if (Array.isArray(value)) return value.map((v) => String(v).trim()).filter(Boolean);
  return String(value)
    .split(/[,;|]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function toDateInput(value) {
  if (!value) return '';
  return String(value).slice(0, 10);
}

function toDateTimeLocal(value) {
  if (!value) return '';
  try {
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return '';
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch {
    return '';
  }
}

function DetailRow({ label, children }) {
  if (children == null || children === '' || children === false) return null;
  if (Array.isArray(children) && children.length === 0) return null;
  return (
    <div className="min-w-0">
      <dt className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-sm text-slate-800 break-words">{children}</dd>
    </div>
  );
}

function TagList({ items, tone = 'slate' }) {
  const list = asList(items);
  if (!list.length) return null;
  const tones = {
    slate: 'bg-slate-100 text-slate-700',
    emerald: 'bg-emerald-50 text-emerald-800',
    amber: 'bg-amber-50 text-amber-800',
    rose: 'bg-rose-50 text-rose-800',
  };
  return (
    <div className="flex flex-wrap gap-1.5">
      {list.map((item) => (
        <span
          key={item}
          className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${tones[tone] || tones.slate}`}
        >
          {item}
        </span>
      ))}
    </div>
  );
}

function Field({ label, children, className = '' }) {
  return (
    <label className={`min-w-0 block ${className}`}>
      <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</span>
      <div className="mt-0.5">{children}</div>
    </label>
  );
}

const inputClass =
  'w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm text-slate-800 outline-none focus:border-[#2CABE3] focus:ring-1 focus:ring-[#2CABE3]';
const checkClass = 'rounded border-slate-300 text-[#2CABE3] focus:ring-[#2CABE3]';

function listingToDraft(listing) {
  if (!listing) return {};
  return {
    title: listing.title || '',
    description: listing.description || '',
    quantity: listing.quantity ?? '',
    unit: listing.unit || '',
    category: listing.category || 'other',
    listing_type: listing.listing_type || 'donation',
    community_id: listing.community_id != null ? String(listing.community_id) : '',
    school_district: listing.school_district || '',
    expiry_date: toDateInput(listing.expiry_date),
    preparation_date: toDateInput(listing.preparation_date),
    pickup_by: toDateTimeLocal(listing.pickup_by),
    urgency_level: listing.urgency_level || '',
    location: listing.full_address || listing.location || '',
    latitude: listing.latitude ?? '',
    longitude: listing.longitude ?? '',
    packaging_type: listing.packaging_type || '',
    current_condition: listing.current_condition || '',
    storage_requirements: listing.storage_requirements || '',
    requires_refrigeration: !!listing.requires_refrigeration,
    requires_freezing: !!listing.requires_freezing,
    is_perishable: !!listing.is_perishable,
    storage_temperature_min: listing.storage_temperature_min ?? '',
    storage_temperature_max: listing.storage_temperature_max ?? '',
    current_storage_temp: listing.current_storage_temp ?? '',
    dietary_tags: asList(listing.dietary_tags).join(', '),
    allergens: asList(listing.allergens || listing.allergen_info).join(', '),
    ingredients: listing.ingredients || '',
    safe_handling_instructions: listing.safe_handling_instructions || '',
    reheating_instructions: listing.reheating_instructions || '',
    safety_notes: listing.safety_notes || '',
    passed_safety_check:
      listing.passed_safety_check == null ? '' : listing.passed_safety_check ? 'true' : 'false',
    safety_check_date: toDateTimeLocal(listing.safety_check_date),
    safety_checked_by: listing.safety_checked_by || '',
    donor_name: listing.donor_name || '',
    donor_email: listing.donor_email || '',
    donor_phone: listing.donor_phone || '',
    donor_type: listing.donor_type || '',
    donor_city: listing.donor_city || '',
    donor_state: listing.donor_state || '',
    donor_zip: listing.donor_zip || '',
    donor_occupation: listing.donor_occupation || '',
    weight_per_package: listing.weight_per_package ?? '',
    weight_unit: listing.weight_unit || '',
    image_url: listing.image_url || '',
    image: null,
  };
}

function draftToPatch(draft) {
  const tags = asList(draft.dietary_tags);
  const allergens = asList(draft.allergens);
  const qty = draft.quantity === '' || draft.quantity == null ? null : Number(draft.quantity);
  const weight =
    draft.weight_per_package === '' || draft.weight_per_package == null
      ? null
      : Number(draft.weight_per_package);
  const numOrNull = (v) => {
    if (v === '' || v == null) return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  };

  let passedSafety = null;
  if (draft.passed_safety_check === 'true') passedSafety = true;
  else if (draft.passed_safety_check === 'false') passedSafety = false;

  const patch = {
    title: String(draft.title || '').trim() || null,
    description: String(draft.description || '').trim() || null,
    quantity: Number.isFinite(qty) ? qty : null,
    unit: String(draft.unit || '').trim() || null,
    category: draft.category || 'other',
    listing_type: LISTING_TYPES.includes(draft.listing_type) ? draft.listing_type : 'donation',
    community_id: draft.community_id ? Number(draft.community_id) : null,
    school_district: String(draft.school_district || '').trim() || null,
    expiry_date: draft.expiry_date || null,
    preparation_date: draft.preparation_date || null,
    pickup_by: draft.pickup_by ? new Date(draft.pickup_by).toISOString() : null,
    urgency_level: draft.urgency_level || null,
    full_address: String(draft.location || '').trim() || null,
    location: String(draft.location || '').trim() || null,
    latitude: numOrNull(draft.latitude),
    longitude: numOrNull(draft.longitude),
    packaging_type: PACKAGING_TYPES.includes(draft.packaging_type) ? draft.packaging_type : null,
    current_condition: CONDITIONS.includes(draft.current_condition) ? draft.current_condition : null,
    storage_requirements: STORAGE_REQUIREMENTS.includes(draft.storage_requirements)
      ? draft.storage_requirements
      : null,
    requires_refrigeration: !!draft.requires_refrigeration,
    requires_freezing: !!draft.requires_freezing,
    is_perishable: !!draft.is_perishable,
    storage_temperature_min: numOrNull(draft.storage_temperature_min),
    storage_temperature_max: numOrNull(draft.storage_temperature_max),
    current_storage_temp: numOrNull(draft.current_storage_temp),
    dietary_tags: tags.length ? tags : null,
    allergens: allergens.length ? allergens : null,
    allergen_info: allergens.length ? allergens : null,
    ingredients: String(draft.ingredients || '').trim() || null,
    safe_handling_instructions: String(draft.safe_handling_instructions || '').trim() || null,
    reheating_instructions: String(draft.reheating_instructions || '').trim() || null,
    safety_notes: String(draft.safety_notes || '').trim() || null,
    passed_safety_check: passedSafety,
    safety_check_date: draft.safety_check_date
      ? new Date(draft.safety_check_date).toISOString()
      : null,
    safety_checked_by: String(draft.safety_checked_by || '').trim() || null,
    donor_name: String(draft.donor_name || '').trim() || null,
    donor_email: String(draft.donor_email || '').trim() || null,
    donor_phone: String(draft.donor_phone || '').trim() || null,
    donor_type: String(draft.donor_type || '').trim() || null,
    donor_city: String(draft.donor_city || '').trim() || null,
    donor_state: String(draft.donor_state || '').trim() || null,
    donor_zip: String(draft.donor_zip || '').trim() || null,
    donor_occupation: String(draft.donor_occupation || '').trim() || null,
    weight_per_package: Number.isFinite(weight) ? weight : null,
    weight_unit: String(draft.weight_unit || '').trim() || null,
  };

  if (String(draft.listing_type || listing?.listing_type || '').toLowerCase() === 'request') {
    patch.image_url = null;
    delete patch.image;
  } else if (draft.image instanceof File) {
    patch.image = draft.image;
  } else if (Object.prototype.hasOwnProperty.call(draft, 'image_url')) {
    const url = String(draft.image_url || '').trim();
    patch.image_url = url || null;
  }

  return patch;
}

function ReadOnlyFoodDetail({ listing, compact }) {
  const community = listing.communities;
  const communityRecord = Array.isArray(community) ? community[0] : community;
  const communityName = communityRecord?.name || listing.community_name || null;
  const address = listing.full_address || listing.location || null;
  const donorUser = listing.users || listing.donor || null;
  const isRequest = String(listing.listing_type || '').toLowerCase() === 'request';
  const personLabel = isRequest ? 'Requester' : 'Donor';

  const donorName = listing.donor_name || donorUser?.name || null;
  const donorEmail = listing.donor_email || donorUser?.email || null;
  const donorPhone = listing.donor_phone || null;
  const qtyLabel = [listing.quantity, listing.unit].filter((v) => v != null && v !== '').join(' ');
  const imageSize = compact ? 'h-16 w-16' : 'h-20 w-20';

  return (
    <div className="flex flex-col sm:flex-row gap-3">
      {!isRequest && (
      <div className="shrink-0">
        {listing.image_url ? (
          <img
            src={listing.image_url}
            alt={listing.title || 'Food'}
            className={`${imageSize} rounded-lg object-cover border border-slate-200 bg-slate-50`}
          />
        ) : (
          <div className={`${imageSize} rounded-lg bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-400`}>
            <i className="fas fa-utensils" aria-hidden="true" />
          </div>
        )}
      </div>
      )}
      {isRequest && (
      <div className="shrink-0">
        <div className={`${imageSize} rounded-lg bg-emerald-50 border border-emerald-100 flex items-center justify-center text-emerald-700`}>
          <i className="fas fa-clipboard-list" aria-hidden="true" />
        </div>
      </div>
      )}
      <div className="min-w-0 flex-1 space-y-2">
        <div>
          <h3 className="text-base font-semibold text-slate-900">{listing.title || 'Untitled food'}</h3>
          {listing.description ? (
            <p className="mt-0.5 text-sm text-slate-600 line-clamp-3 whitespace-pre-wrap">{listing.description}</p>
          ) : null}
        </div>
        <dl className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-2">
          <DetailRow label="Quantity">{qtyLabel || '—'}</DetailRow>
          <DetailRow label="Category">
            <span className="capitalize">{listing.category || 'other'}</span>
          </DetailRow>
          <DetailRow label="Type">
            <span className="capitalize">{listing.listing_type || 'donation'}</span>
          </DetailRow>
          <DetailRow label="Community">{communityName}</DetailRow>
          <DetailRow label={isRequest ? 'Needed by' : 'Expires'}>{formatDateOnly(listing.expiry_date)}</DetailRow>
          <DetailRow label={isRequest ? 'Preferred by' : 'Pickup by'}>{formatDate(listing.pickup_by)}</DetailRow>
          <DetailRow label="Address">{address}</DetailRow>
          <DetailRow label={personLabel}>{donorName}</DetailRow>
          <DetailRow label="Email">{donorEmail}</DetailRow>
          <DetailRow label="Phone">{donorPhone}</DetailRow>
          <DetailRow label="Dietary">
            <TagList items={listing.dietary_tags} tone="emerald" />
          </DetailRow>
          <DetailRow label="Allergens">
            <TagList items={listing.allergens || listing.allergen_info} tone="rose" />
          </DetailRow>
        </dl>
      </div>
    </div>
  );
}

/**
 * Compact food listing editor for admin approval queues.
 * Core fields always visible; extras behind "Show more fields".
 */
export default function AdminFoodDetail({ listing, compact = false, editable = false, onSaved, disabled = false }) {
  const [draft, setDraft] = React.useState(() => listingToDraft(listing));
  const [dirty, setDirty] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [communities, setCommunities] = React.useState([]);
  const [showMore, setShowMore] = React.useState(false);
  const [filePreviewUrl, setFilePreviewUrl] = React.useState(null);

  React.useEffect(() => {
    setDraft(listingToDraft(listing));
    setDirty(false);
    setShowMore(false);
  }, [listing?.id, listing?.updated_at, listing?.title, listing?.quantity, listing?.location, listing?.full_address]);

  React.useEffect(() => {
    if (!editable) return undefined;
    let cancelled = false;
    (async () => {
      try {
        const { data, error } = await supabase
          .from('communities')
          .select('id, name')
          .eq('is_active', true)
          .order('name', { ascending: true });
        if (error) throw error;
        if (!cancelled) setCommunities(data || []);
      } catch (err) {
        console.warn('AdminFoodDetail communities:', err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [editable]);

  React.useEffect(() => {
    if (!(draft.image instanceof File)) {
      setFilePreviewUrl(null);
      return undefined;
    }
    const url = URL.createObjectURL(draft.image);
    setFilePreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [draft.image]);

  if (!listing || typeof listing !== 'object') {
    return <p className="text-sm text-slate-500">No food details available.</p>;
  }

  if (!editable) {
    return <ReadOnlyFoodDetail listing={listing} compact={compact} />;
  }

  const setField = (key, value) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
    setDirty(true);
  };

  const handleSave = async () => {
    if (!listing.id) {
      toast.error('Cannot save — listing id missing');
      return;
    }
    setSaving(true);
    try {
      const patch = draftToPatch(draft);
      if (!patch.title) {
        toast.error('Title is required');
        return;
      }
      const updated = await dataService.updateFoodListing(listing.id, patch);
      setDirty(false);
      const community = communities.find((c) => String(c.id) === String(updated.community_id));
      onSaved?.({
        ...listing,
        ...updated,
        communities: community
          ? { id: community.id, name: community.name }
          : listing.communities,
      });
      toast.success('Saved');
    } catch (err) {
      console.error('Admin listing save failed:', err);
      toast.error(err?.message || 'Could not save listing');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setDraft(listingToDraft(listing));
    setDirty(false);
  };

  const busy = disabled || saving;
  const isRequest = String(draft.listing_type || listing.listing_type || '').toLowerCase() === 'request';
  const personLabel = isRequest ? 'Requester' : 'Donor';
  const imagePreview = filePreviewUrl || draft.image_url || listing.image_url || null;

  return (
    <div className="space-y-3">
      <div className="flex gap-3">
        {!isRequest && (
        <div className="shrink-0 w-20 space-y-1">
          {imagePreview ? (
            <img
              src={imagePreview}
              alt={draft.title || 'Food'}
              className="h-20 w-20 rounded-lg object-cover border border-slate-200 bg-slate-50"
            />
          ) : (
            <div className="h-20 w-20 rounded-lg bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-400">
              <i className="fas fa-utensils" aria-hidden="true" />
            </div>
          )}
          <input
            type="file"
            accept="image/*"
            disabled={busy}
            aria-label="Change photo"
            onChange={(e) => {
              const file = e.target.files?.[0] || null;
              setField('image', file);
              if (file) setField('image_url', '');
            }}
            className="block w-full text-[10px] text-slate-500 file:mr-1 file:rounded file:border-0 file:bg-slate-100 file:px-1.5 file:py-0.5 file:text-[10px]"
          />
        </div>
        )}
        {isRequest && (
        <div className="shrink-0 w-20">
          <div className="h-20 w-20 rounded-lg bg-emerald-50 border border-emerald-100 flex items-center justify-center text-emerald-700">
            <i className="fas fa-clipboard-list text-xl" aria-hidden="true" />
          </div>
          <p className="mt-1 text-[10px] text-slate-500 text-center">No photo</p>
        </div>
        )}
        <div className="min-w-0 flex-1 space-y-2">
          <Field label="Title">
            <input type="text" value={draft.title} onChange={(e) => setField('title', e.target.value)} disabled={busy} className={inputClass} />
          </Field>
          <Field label="Description">
            <textarea rows={2} value={draft.description} onChange={(e) => setField('description', e.target.value)} disabled={busy} className={inputClass} />
          </Field>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
        <Field label="Quantity">
          <input type="number" step="any" min="0" value={draft.quantity} onChange={(e) => setField('quantity', e.target.value)} disabled={busy} className={inputClass} />
        </Field>
        <Field label="Unit">
          <input type="text" value={draft.unit} onChange={(e) => setField('unit', e.target.value)} disabled={busy} className={inputClass} placeholder="items, lb…" />
        </Field>
        <Field label="Category">
          <select value={draft.category} onChange={(e) => setField('category', e.target.value)} disabled={busy} className={inputClass}>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </Field>
        <Field label="Community">
          <select value={draft.community_id} onChange={(e) => setField('community_id', e.target.value)} disabled={busy} className={inputClass}>
            <option value="">Choose…</option>
            {communities.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </Field>
        <Field label={isRequest ? 'Needed by' : 'Expires'}>
          <input type="date" value={draft.expiry_date} onChange={(e) => setField('expiry_date', e.target.value)} disabled={busy} className={inputClass} />
        </Field>
        <Field label={isRequest ? 'Preferred by' : 'Pickup by'}>
          <input type="datetime-local" value={draft.pickup_by} onChange={(e) => setField('pickup_by', e.target.value)} disabled={busy} className={inputClass} />
        </Field>
        <Field label={isRequest ? 'Address' : 'Pickup address'} className="col-span-2 sm:col-span-3">
          <input type="text" value={draft.location} onChange={(e) => setField('location', e.target.value)} disabled={busy} className={inputClass} />
        </Field>
        <Field label={personLabel}>
          <input type="text" value={draft.donor_name} onChange={(e) => setField('donor_name', e.target.value)} disabled={busy} className={inputClass} />
        </Field>
        <Field label="Email">
          <input type="email" value={draft.donor_email} onChange={(e) => setField('donor_email', e.target.value)} disabled={busy} className={inputClass} />
        </Field>
        <Field label="Phone">
          <input type="text" value={draft.donor_phone} onChange={(e) => setField('donor_phone', e.target.value)} disabled={busy} className={inputClass} />
        </Field>
      </div>

      <button
        type="button"
        onClick={() => setShowMore((v) => !v)}
        className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#1a7a9e] hover:text-[#156a8a]"
      >
        <i className={`fas fa-chevron-${showMore ? 'up' : 'down'} text-[10px]`} aria-hidden="true" />
        {showMore ? 'Hide extra fields' : 'Show more fields'}
      </button>

      {showMore && (
        <div className="space-y-3 rounded-xl border border-slate-100 bg-slate-50/60 p-3">
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
            <Field label="Listing type">
              <select value={draft.listing_type} onChange={(e) => setField('listing_type', e.target.value)} disabled={busy} className={inputClass}>
                {LISTING_TYPES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </Field>
            <Field label="Urgency">
              <select value={draft.urgency_level} onChange={(e) => setField('urgency_level', e.target.value)} disabled={busy} className={inputClass}>
                <option value="">—</option>
                {URGENCY.map((u) => (
                  <option key={u} value={u}>{u}</option>
                ))}
              </select>
            </Field>
            <Field label="Prepared">
              <input type="date" value={draft.preparation_date} onChange={(e) => setField('preparation_date', e.target.value)} disabled={busy} className={inputClass} />
            </Field>
            <Field label="School district">
              <input type="text" value={draft.school_district} onChange={(e) => setField('school_district', e.target.value)} disabled={busy} className={inputClass} />
            </Field>
            <Field label="Latitude">
              <input type="number" step="any" value={draft.latitude} onChange={(e) => setField('latitude', e.target.value)} disabled={busy} className={inputClass} />
            </Field>
            <Field label="Longitude">
              <input type="number" step="any" value={draft.longitude} onChange={(e) => setField('longitude', e.target.value)} disabled={busy} className={inputClass} />
            </Field>
            <Field label="Weight">
              <input type="number" step="any" min="0" value={draft.weight_per_package} onChange={(e) => setField('weight_per_package', e.target.value)} disabled={busy} className={inputClass} />
            </Field>
            <Field label="Weight unit">
              <input type="text" value={draft.weight_unit} onChange={(e) => setField('weight_unit', e.target.value)} disabled={busy} className={inputClass} />
            </Field>
            <Field label="Packaging">
              <select value={draft.packaging_type} onChange={(e) => setField('packaging_type', e.target.value)} disabled={busy} className={inputClass}>
                <option value="">—</option>
                {PACKAGING_TYPES.map((c) => (
                  <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>
                ))}
              </select>
            </Field>
            <Field label="Condition">
              <select value={draft.current_condition} onChange={(e) => setField('current_condition', e.target.value)} disabled={busy} className={inputClass}>
                <option value="">—</option>
                {CONDITIONS.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </Field>
            <Field label="Storage">
              <select value={draft.storage_requirements} onChange={(e) => setField('storage_requirements', e.target.value)} disabled={busy} className={inputClass}>
                <option value="">—</option>
                {STORAGE_REQUIREMENTS.map((c) => (
                  <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>
                ))}
              </select>
            </Field>
            <Field label="Temp min">
              <input type="number" step="any" value={draft.storage_temperature_min} onChange={(e) => setField('storage_temperature_min', e.target.value)} disabled={busy} className={inputClass} />
            </Field>
            <Field label="Temp max">
              <input type="number" step="any" value={draft.storage_temperature_max} onChange={(e) => setField('storage_temperature_max', e.target.value)} disabled={busy} className={inputClass} />
            </Field>
            <Field label="Current temp">
              <input type="number" step="any" value={draft.current_storage_temp} onChange={(e) => setField('current_storage_temp', e.target.value)} disabled={busy} className={inputClass} />
            </Field>
            <Field label="Dietary tags" className="sm:col-span-2">
              <input type="text" value={draft.dietary_tags} onChange={(e) => setField('dietary_tags', e.target.value)} disabled={busy} className={inputClass} placeholder="comma-separated" />
            </Field>
            <Field label="Allergens">
              <input type="text" value={draft.allergens} onChange={(e) => setField('allergens', e.target.value)} disabled={busy} className={inputClass} placeholder="comma-separated" />
            </Field>
            <Field label="Ingredients" className="col-span-2 sm:col-span-3">
              <textarea rows={2} value={draft.ingredients} onChange={(e) => setField('ingredients', e.target.value)} disabled={busy} className={inputClass} />
            </Field>
            <Field label="Safe handling">
              <textarea rows={2} value={draft.safe_handling_instructions} onChange={(e) => setField('safe_handling_instructions', e.target.value)} disabled={busy} className={inputClass} />
            </Field>
            <Field label="Reheating">
              <textarea rows={2} value={draft.reheating_instructions} onChange={(e) => setField('reheating_instructions', e.target.value)} disabled={busy} className={inputClass} />
            </Field>
            <Field label="Safety notes">
              <textarea rows={2} value={draft.safety_notes} onChange={(e) => setField('safety_notes', e.target.value)} disabled={busy} className={inputClass} />
            </Field>
            <Field label="Safety check">
              <select value={draft.passed_safety_check} onChange={(e) => setField('passed_safety_check', e.target.value)} disabled={busy} className={inputClass}>
                <option value="">—</option>
                <option value="true">Passed</option>
                <option value="false">Not passed</option>
              </select>
            </Field>
            <Field label="Safety check date">
              <input type="datetime-local" value={draft.safety_check_date} onChange={(e) => setField('safety_check_date', e.target.value)} disabled={busy} className={inputClass} />
            </Field>
            <Field label="Checked by">
              <input type="text" value={draft.safety_checked_by} onChange={(e) => setField('safety_checked_by', e.target.value)} disabled={busy} className={inputClass} />
            </Field>
            <Field label="Org / type">
              <input type="text" value={draft.donor_type} onChange={(e) => setField('donor_type', e.target.value)} disabled={busy} className={inputClass} />
            </Field>
            <Field label="City">
              <input type="text" value={draft.donor_city} onChange={(e) => setField('donor_city', e.target.value)} disabled={busy} className={inputClass} />
            </Field>
            <Field label="State">
              <input type="text" value={draft.donor_state} onChange={(e) => setField('donor_state', e.target.value)} disabled={busy} className={inputClass} />
            </Field>
            <Field label="ZIP">
              <input type="text" value={draft.donor_zip} onChange={(e) => setField('donor_zip', e.target.value)} disabled={busy} className={inputClass} />
            </Field>
            <Field label="Occupation">
              <input type="text" value={draft.donor_occupation} onChange={(e) => setField('donor_occupation', e.target.value)} disabled={busy} className={inputClass} />
            </Field>
          </div>
          <div className="flex flex-wrap gap-4 text-sm text-slate-700">
            <label className="inline-flex items-center gap-2">
              <input type="checkbox" checked={draft.requires_refrigeration} onChange={(e) => setField('requires_refrigeration', e.target.checked)} disabled={busy} className={checkClass} />
              Refrigeration
            </label>
            <label className="inline-flex items-center gap-2">
              <input type="checkbox" checked={draft.requires_freezing} onChange={(e) => setField('requires_freezing', e.target.checked)} disabled={busy} className={checkClass} />
              Freezing
            </label>
            <label className="inline-flex items-center gap-2">
              <input type="checkbox" checked={draft.is_perishable} onChange={(e) => setField('is_perishable', e.target.checked)} disabled={busy} className={checkClass} />
              Perishable
            </label>
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-end gap-2 pt-1 border-t border-slate-100">
        {dirty ? (
          <span className="mr-auto text-xs text-amber-700">Unsaved changes</span>
        ) : (
          <span className="mr-auto text-xs text-slate-400">Edit essentials, then approve</span>
        )}
        <button type="button" onClick={handleReset} disabled={busy || !dirty} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-40">
          Reset
        </button>
        <button type="button" onClick={handleSave} disabled={busy || !dirty} className="rounded-lg bg-[#2CABE3] px-3 py-1.5 text-sm font-medium text-white hover:bg-[#2596c7] disabled:opacity-40">
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </div>
  );
}
