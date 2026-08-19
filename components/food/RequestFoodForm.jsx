import React, { useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import Input from '../common/Input';
import Button from '../common/Button';
import { useAuthContext } from '../../utils/AuthContext';
import dataService from '../../utils/dataService';
import supabase from '../../utils/supabaseClient';
import useFormVoiceGuide, { REQUEST_FOOD_STEPS, REQUEST_FOOD_HINTS } from '../../hooks/useFormVoiceGuide';
import FormVoiceGuide from '../common/FormVoiceGuide';

const CATEGORIES = [
  { value: '', label: 'Select category' },
  { value: 'produce', label: 'Fresh Produce' },
  { value: 'dairy', label: 'Dairy' },
  { value: 'bakery', label: 'Bakery' },
  { value: 'pantry', label: 'Pantry Items' },
  { value: 'meat', label: 'Meat & Poultry' },
  { value: 'seafood', label: 'Seafood' },
  { value: 'frozen', label: 'Frozen' },
  { value: 'snacks', label: 'Snacks' },
  { value: 'beverages', label: 'Beverages' },
  { value: 'prepared', label: 'Prepared Foods' },
  { value: 'other', label: 'Other' },
];

const UNITS = [
  { value: 'items', label: 'Items / portions' },
  { value: 'lb', label: 'Pounds (lb)' },
  { value: 'serving', label: 'Servings' },
  { value: 'bags', label: 'Bags' },
  { value: 'boxes', label: 'Boxes' },
];

/**
 * Form for recipients to request food that isn't currently on Find Food.
 * Submits as food_listings with listing_type: 'request'.
 */
function RequestFoodForm({ onSubmit, loading = false }) {
  const { user } = useAuthContext();
  const [communities, setCommunities] = useState([]);
  const [loadingCommunities, setLoadingCommunities] = useState(true);
  const [requireApproval, setRequireApproval] = useState(true);
  const [errors, setErrors] = useState({});
  const guide = useFormVoiceGuide({ steps: REQUEST_FOOD_STEPS, formData, hints: REQUEST_FOOD_HINTS });
  const { speakField } = guide;
  const [formData, setFormData] = useState({
    title: '',
    category: '',
    quantity: '1',
    unit: 'items',
    description: '',
    dietary_notes: '',
    needed_by: '',
    school_district: '',
    requester_name: '',
    requester_email: '',
    requester_phone: '',
    full_address: '',
  });

  useEffect(() => {
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
        console.error('RequestFoodForm communities:', err);
        if (!cancelled) setCommunities([]);
      } finally {
        if (!cancelled) setLoadingCommunities(false);
      }
    })();
    dataService.getRequireRequestApproval()
      .then((v) => { if (!cancelled) setRequireApproval(!!v); })
      .catch(() => { if (!cancelled) setRequireApproval(true); });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!user) return;
    setFormData((prev) => {
      const userCommunity = communities.find(
        (c) => String(c.id) === String(user.community_id)
      );
      return {
        ...prev,
        requester_name: prev.requester_name || user.name || '',
        requester_email: prev.requester_email || user.email || '',
        requester_phone: prev.requester_phone || user.phone || '',
        full_address: prev.full_address || user.address || '',
        school_district:
          prev.school_district
          || userCommunity?.name
          || user.community_name
          || '',
      };
    });
  }, [user, communities]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    if (errors[name]) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[name];
        return next;
      });
    }
  };

  const validate = () => {
    const next = {};
    if (!String(formData.title || '').trim()) next.title = 'What food do you need?';
    if (!formData.category) next.category = 'Category is required';
    const qty = Number(formData.quantity);
    if (!Number.isFinite(qty) || qty <= 0) next.quantity = 'Enter how much you need';
    if (!String(formData.school_district || '').trim()) {
      next.school_district = 'Choose your school or community';
    }
    if (!String(formData.requester_name || '').trim()) next.requester_name = 'Name is required';
    if (!String(formData.requester_email || '').trim()) next.requester_email = 'Email is required';
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!validate()) return;

    const dietary = String(formData.dietary_notes || '')
      .split(/[,;]/)
      .map((s) => s.trim())
      .filter(Boolean);

    const notes = [
      String(formData.description || '').trim(),
      formData.dietary_notes
        ? `Dietary needs: ${String(formData.dietary_notes).trim()}`
        : '',
    ]
      .filter(Boolean)
      .join('\n\n');

    onSubmit?.({
      title: String(formData.title).trim(),
      description: notes || `Looking for ${formData.title}`,
      quantity: Number(formData.quantity),
      unit: formData.unit || 'items',
      category: formData.category,
      expiry_date: formData.needed_by || null,
      pickup_by: formData.needed_by ? `${formData.needed_by}T23:59:00` : null,
      school_district: formData.school_district,
      donor_name: String(formData.requester_name).trim(),
      donor_email: String(formData.requester_email).trim(),
      donor_phone: String(formData.requester_phone || '').trim() || null,
      full_address: String(formData.full_address || '').trim() || null,
      listing_type: 'request',
      dietary_tags: dietary,
      allergens: [],
    });
  };

  const communityLocked = Boolean(user?.community_id) && communities.some(
    (c) => String(c.id) === String(user.community_id)
  );

  return (
    <form onSubmit={handleSubmit} className="space-y-6" noValidate>
      <FormVoiceGuide guide={guide} className="mb-2" />
      <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
        <p className="font-semibold">Can’t find what you need on Find Food?</p>
        <p className="mt-1 text-amber-900/90">
          Tell the community what you’re looking for. Donors and organizers in your
          school/community can see open requests and share matching food.
        </p>
        <p className="mt-2 text-amber-900/90">
          {requireApproval
            ? 'Your request will wait for admin approval before it appears on Community Requests.'
            : 'Your request goes live on Community Requests right away.'}
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="md:col-span-2">
          <Input
            label="What food do you need?"
            name="title"
            value={formData.title}
            onChange={handleChange}
            onFocus={() => speakField('title')}
            error={errors.title}
            required
            placeholder="e.g. Rice, fresh vegetables, baby formula"
          />
        </div>

        <Input
          label="Category"
          name="category"
          type="select"
          value={formData.category}
          onChange={handleChange}
          onFocus={() => speakField('category')}
          error={errors.category}
          required
          options={CATEGORIES}
        />

        <div className="grid grid-cols-2 gap-3">
          <Input
            label="How much?"
            name="quantity"
            type="number"
            min="0.1"
            step="any"
            value={formData.quantity}
            onChange={handleChange}
            onFocus={() => speakField('quantity')}
            error={errors.quantity}
            required
          />
          <Input
            label="Unit"
            name="unit"
            type="select"
            value={formData.unit}
            onChange={handleChange}
            onFocus={() => speakField('unit')}
            options={UNITS}
          />
        </div>

        <Input
          label="Needed by (optional)"
          name="needed_by"
          type="date"
          value={formData.needed_by}
          onChange={handleChange}
          onFocus={() => speakField('needed_by')}
          helperText="When do you need this by?"
        />

        <Input
          label="School / community"
          name="school_district"
          type="select"
          value={formData.school_district}
          onChange={handleChange}
          onFocus={() => speakField('school_district')}
          error={errors.school_district}
          required
          disabled={loadingCommunities || communityLocked}
          options={[
            { value: '', label: loadingCommunities ? 'Loading…' : 'Choose school or community' },
            ...communities.map((c) => ({ value: c.name, label: c.name })),
          ]}
        />

        <div className="md:col-span-2">
          <Input
            label="Details (optional)"
            name="description"
            type="textarea"
            value={formData.description}
            onChange={handleChange}
            onFocus={() => speakField('description')}
            placeholder="Household size, preferred pickup area, why you need it…"
          />
        </div>

        <div className="md:col-span-2">
          <Input
            label="Dietary needs (optional)"
            name="dietary_notes"
            value={formData.dietary_notes}
            onChange={handleChange}
            onFocus={() => speakField('dietary_notes')}
            placeholder="e.g. gluten-free, vegetarian, nut allergy"
            helperText="Separate multiple needs with commas"
          />
        </div>

        <Input
          label="Your name"
          name="requester_name"
          value={formData.requester_name}
          onChange={handleChange}
          onFocus={() => speakField('requester_name')}
          error={errors.requester_name}
          required
        />
        <Input
          label="Email"
          name="requester_email"
          type="email"
          value={formData.requester_email}
          onChange={handleChange}
          onFocus={() => speakField('requester_email')}
          error={errors.requester_email}
          required
        />
        <Input
          label="Phone (optional)"
          name="requester_phone"
          value={formData.requester_phone}
          onChange={handleChange}
          onFocus={() => speakField('requester_phone')}
        />
        <Input
          label="Preferred pickup area (optional)"
          name="full_address"
          value={formData.full_address}
          onChange={handleChange}
          onFocus={() => speakField('full_address')}
          placeholder="Neighborhood or address"
        />
      </div>

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-end gap-3 pt-2">
        <Button type="submit" variant="primary" loading={loading} disabled={loading}>
          {loading ? 'Submitting…' : 'Submit food request'}
        </Button>
      </div>
    </form>
  );
}

RequestFoodForm.propTypes = {
  onSubmit: PropTypes.func.isRequired,
  loading: PropTypes.bool,
};

export default RequestFoodForm;
