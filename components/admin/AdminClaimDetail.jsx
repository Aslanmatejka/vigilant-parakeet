import React from 'react';
import { toast } from 'react-toastify';
import dataService from '../../utils/dataService';

function formatDate(dateString) {
  if (!dateString) return '—';
  return new Date(dateString).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function toDateInput(value) {
  if (!value) return '';
  return String(value).slice(0, 10);
}

function toTimeInput(value) {
  if (!value) return '';
  const raw = String(value);
  // Postgres time may be "HH:MM:SS" or "HH:MM:SS.mmm"
  const match = raw.match(/^(\d{1,2}):(\d{2})/);
  if (!match) return '';
  return `${match[1].padStart(2, '0')}:${match[2]}`;
}

const inputClass =
  'w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm text-slate-800 outline-none focus:border-[#2CABE3] focus:ring-1 focus:ring-[#2CABE3]';

function Field({ label, children, className = '' }) {
  return (
    <label className={`min-w-0 block ${className}`}>
      <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</span>
      <div className="mt-0.5">{children}</div>
    </label>
  );
}

function claimToDraft(claim) {
  if (!claim) return {};
  return {
    quantity: claim.quantity ?? '',
    requester_name: claim.requester_name || '',
    requester_email: claim.requester_email || '',
    requester_phone: claim.requester_phone || '',
    school: claim.school || '',
    school_district: claim.school_district || '',
    school_contact: claim.school_contact || '',
    school_contact_email: claim.school_contact_email || '',
    school_contact_phone: claim.school_contact_phone || '',
    members_count: claim.members_count ?? '',
    people: claim.people ?? '',
    students: claim.students ?? '',
    school_staff: claim.school_staff ?? '',
    dietary_restrictions: claim.dietary_restrictions || '',
    pickup_date: toDateInput(claim.pickup_date),
    pickup_time: toTimeInput(claim.pickup_time),
    pickup_place: claim.pickup_place || '',
    pickup_contact: claim.pickup_contact || '',
    dropoff_place: claim.dropoff_place || '',
    dropoff_time: toTimeInput(claim.dropoff_time),
    dropoff_contact: claim.dropoff_contact || '',
  };
}

function draftToPatch(draft) {
  const numOrNull = (v) => {
    if (v === '' || v == null) return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  };
  const intOrNull = (v) => {
    const n = numOrNull(v);
    return n == null ? null : Math.round(n);
  };

  return {
    quantity: intOrNull(draft.quantity),
    requester_name: String(draft.requester_name || '').trim() || null,
    requester_email: String(draft.requester_email || '').trim() || null,
    requester_phone: String(draft.requester_phone || '').trim() || null,
    school: String(draft.school || '').trim() || null,
    school_district: String(draft.school_district || '').trim() || null,
    school_contact: String(draft.school_contact || '').trim() || null,
    school_contact_email: String(draft.school_contact_email || '').trim() || null,
    school_contact_phone: String(draft.school_contact_phone || '').trim() || null,
    members_count: intOrNull(draft.members_count),
    people: intOrNull(draft.people),
    students: intOrNull(draft.students),
    school_staff: intOrNull(draft.school_staff),
    dietary_restrictions: String(draft.dietary_restrictions || '').trim() || null,
    pickup_date: draft.pickup_date || null,
    pickup_time: draft.pickup_time ? `${draft.pickup_time}:00` : null,
    pickup_place: String(draft.pickup_place || '').trim() || null,
    pickup_contact: String(draft.pickup_contact || '').trim() || null,
    dropoff_place: String(draft.dropoff_place || '').trim() || null,
    dropoff_time: draft.dropoff_time ? `${draft.dropoff_time}:00` : null,
    dropoff_contact: String(draft.dropoff_contact || '').trim() || null,
  };
}

/**
 * Editable claim fields for the admin claim approval queue.
 */
export default function AdminClaimDetail({ claim, listing, editable = false, onSaved, disabled = false }) {
  const [draft, setDraft] = React.useState(() => claimToDraft(claim));
  const [dirty, setDirty] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [showMore, setShowMore] = React.useState(false);

  React.useEffect(() => {
    setDraft(claimToDraft(claim));
    setDirty(false);
  }, [claim?.id, claim?.updated_at, claim?.quantity, claim?.requester_name]);

  if (!claim) {
    return <p className="text-sm text-slate-500">No claim details available.</p>;
  }

  if (!editable) {
    const rows = [
      { label: 'Claim quantity', value: [claim.quantity, listing?.unit].filter((v) => v != null && v !== '').join(' ') || '—' },
      { label: 'Claimant', value: claim.requester_name },
      { label: 'Email', value: claim.requester_email },
      { label: 'Phone', value: claim.requester_phone },
      { label: 'School', value: claim.school },
      { label: 'School district', value: claim.school_district },
      { label: 'School contact', value: claim.school_contact },
      { label: 'School contact email', value: claim.school_contact_email },
      { label: 'School contact phone', value: claim.school_contact_phone },
      { label: 'Household / members', value: claim.members_count ?? claim.people },
      { label: 'Students', value: claim.students },
      { label: 'School staff', value: claim.school_staff },
      { label: 'Dietary restrictions', value: claim.dietary_restrictions },
      { label: 'Pickup date', value: claim.pickup_date ? toDateInput(claim.pickup_date) : null },
      { label: 'Pickup time', value: claim.pickup_time },
      { label: 'Pickup place', value: claim.pickup_place },
      { label: 'Pickup contact', value: claim.pickup_contact },
      { label: 'Drop-off place', value: claim.dropoff_place },
      { label: 'Drop-off time', value: claim.dropoff_time },
      { label: 'Drop-off contact', value: claim.dropoff_contact },
      { label: 'Submitted', value: formatDate(claim.created_at || claim.claimed_at) },
    ].filter((row) => row.value != null && row.value !== '');

    return (
      <div className="rounded-xl border border-rose-100 bg-rose-50/40 p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-rose-700 mb-3">
          Claim details
        </p>
        <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-4 gap-y-3">
          {rows.map((row) => (
            <div key={row.label} className="min-w-0">
              <dt className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                {row.label}
              </dt>
              <dd className="mt-0.5 text-sm text-slate-800 break-words">{row.value}</dd>
            </div>
          ))}
        </dl>
      </div>
    );
  }

  const setField = (key, value) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
    setDirty(true);
  };

  const busy = disabled || saving;

  const handleSave = async () => {
    if (!claim.id) {
      toast.error('Cannot save — claim id missing');
      return;
    }
    setSaving(true);
    try {
      const patch = draftToPatch(draft);
      if (patch.quantity == null || patch.quantity < 1) {
        toast.error('Claim quantity must be at least 1');
        return;
      }
      if (!patch.requester_name) {
        toast.error('Claimant name is required');
        return;
      }
      const result = await dataService.updateFoodClaim(claim.id, patch);
      setDirty(false);
      onSaved?.(result);
      toast.success('Claim saved');
    } catch (err) {
      console.error('Admin claim save failed:', err);
      toast.error(err?.message || 'Could not save claim');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setDraft(claimToDraft(claim));
    setDirty(false);
  };

  return (
    <div className="rounded-xl border border-rose-100 bg-rose-50/40 p-4 space-y-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-rose-700">
        Claim details
      </p>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
        <Field label={`Qty${listing?.unit ? ` (${listing.unit})` : ''}`}>
          <input
            type="number"
            min="1"
            step="1"
            value={draft.quantity}
            onChange={(e) => setField('quantity', e.target.value)}
            disabled={busy}
            className={inputClass}
          />
        </Field>
        <Field label="Claimant">
          <input type="text" value={draft.requester_name} onChange={(e) => setField('requester_name', e.target.value)} disabled={busy} className={inputClass} />
        </Field>
        <Field label="Email">
          <input type="email" value={draft.requester_email} onChange={(e) => setField('requester_email', e.target.value)} disabled={busy} className={inputClass} />
        </Field>
        <Field label="Phone">
          <input type="text" value={draft.requester_phone} onChange={(e) => setField('requester_phone', e.target.value)} disabled={busy} className={inputClass} />
        </Field>
        <Field label="Pickup date">
          <input type="date" value={draft.pickup_date} onChange={(e) => setField('pickup_date', e.target.value)} disabled={busy} className={inputClass} />
        </Field>
        <Field label="Pickup time">
          <input type="time" value={draft.pickup_time} onChange={(e) => setField('pickup_time', e.target.value)} disabled={busy} className={inputClass} />
        </Field>
        <Field label="Pickup place" className="col-span-2 sm:col-span-3">
          <input type="text" value={draft.pickup_place} onChange={(e) => setField('pickup_place', e.target.value)} disabled={busy} className={inputClass} />
        </Field>
      </div>

      <button
        type="button"
        onClick={() => setShowMore((v) => !v)}
        className="inline-flex items-center gap-1.5 text-xs font-semibold text-rose-800 hover:text-rose-950"
      >
        <i className={`fas fa-chevron-${showMore ? 'up' : 'down'} text-[10px]`} aria-hidden="true" />
        {showMore ? 'Hide extra fields' : 'Show more fields'}
      </button>

      {showMore && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 rounded-lg border border-rose-100 bg-white/50 p-3">
          <Field label="School">
            <input type="text" value={draft.school} onChange={(e) => setField('school', e.target.value)} disabled={busy} className={inputClass} />
          </Field>
          <Field label="School district">
            <input type="text" value={draft.school_district} onChange={(e) => setField('school_district', e.target.value)} disabled={busy} className={inputClass} />
          </Field>
          <Field label="School contact">
            <input type="text" value={draft.school_contact} onChange={(e) => setField('school_contact', e.target.value)} disabled={busy} className={inputClass} />
          </Field>
          <Field label="School contact email">
            <input type="email" value={draft.school_contact_email} onChange={(e) => setField('school_contact_email', e.target.value)} disabled={busy} className={inputClass} />
          </Field>
          <Field label="School contact phone">
            <input type="text" value={draft.school_contact_phone} onChange={(e) => setField('school_contact_phone', e.target.value)} disabled={busy} className={inputClass} />
          </Field>
          <Field label="Household / members">
            <input type="number" min="0" value={draft.members_count} onChange={(e) => setField('members_count', e.target.value)} disabled={busy} className={inputClass} />
          </Field>
          <Field label="People">
            <input type="number" min="0" value={draft.people} onChange={(e) => setField('people', e.target.value)} disabled={busy} className={inputClass} />
          </Field>
          <Field label="Students">
            <input type="number" min="0" value={draft.students} onChange={(e) => setField('students', e.target.value)} disabled={busy} className={inputClass} />
          </Field>
          <Field label="School staff">
            <input type="number" min="0" value={draft.school_staff} onChange={(e) => setField('school_staff', e.target.value)} disabled={busy} className={inputClass} />
          </Field>
          <Field label="Dietary restrictions" className="col-span-2 sm:col-span-3">
            <input type="text" value={draft.dietary_restrictions} onChange={(e) => setField('dietary_restrictions', e.target.value)} disabled={busy} className={inputClass} />
          </Field>
          <Field label="Pickup contact">
            <input type="text" value={draft.pickup_contact} onChange={(e) => setField('pickup_contact', e.target.value)} disabled={busy} className={inputClass} />
          </Field>
          <Field label="Drop-off place">
            <input type="text" value={draft.dropoff_place} onChange={(e) => setField('dropoff_place', e.target.value)} disabled={busy} className={inputClass} />
          </Field>
          <Field label="Drop-off time">
            <input type="time" value={draft.dropoff_time} onChange={(e) => setField('dropoff_time', e.target.value)} disabled={busy} className={inputClass} />
          </Field>
          <Field label="Drop-off contact">
            <input type="text" value={draft.dropoff_contact} onChange={(e) => setField('dropoff_contact', e.target.value)} disabled={busy} className={inputClass} />
          </Field>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
        {dirty ? (
          <span className="mr-auto text-xs text-amber-800">Unsaved changes</span>
        ) : (
          <span className="mr-auto text-xs text-rose-700/70">Edit essentials, then approve</span>
        )}
        <button
          type="button"
          onClick={handleReset}
          disabled={busy || !dirty}
          className="rounded-lg border border-rose-200 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-rose-50 disabled:opacity-40"
        >
          Reset
        </button>
        <button
          type="button"
          onClick={handleSave}
          disabled={busy || !dirty}
          className="rounded-lg bg-rose-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-rose-700 disabled:opacity-40"
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </div>
  );
}
