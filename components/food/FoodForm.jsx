import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import Input from '../common/Input';
import Button from '../common/Button';
import { useAuthContext } from '../../utils/AuthContext';
import supabase from '../../utils/supabaseClient';
import { API_CONFIG } from '../../utils/config';

function FoodForm({
    initialData = null,
    onSubmit,
    loading = false
}) {
    const { user } = useAuthContext();
    const [communities, setCommunities] = useState([]);
    const [loadingCommunities, setLoadingCommunities] = useState(true);
    
    const [formData, setFormData] = useState({
        title: '',
        description: '',
        quantity: '',
        unit: 'lb', // Only pounds allowed
        category: '',
        expiry_date: '',
        pickup_by: '',
        donor_type: '', // 'individual' or 'organization'
        donor_name: '',
        donor_occupation: '',
        donor_zip: '',
        donor_city: '',
        donor_state: '',
        school_district: '',
        donor_email: '',
        donor_phone: '',
        full_address: '',
        latitude: null,
        longitude: null,
        image: null,
        status: 'pending',
        dietary_tags: [],
        allergens: [],
        ingredients: '',
        ...initialData
    });

    const [geocoding, setGeocoding] = useState(false);

    // Fetch active communities from database
    useEffect(() => {
        const fetchCommunities = async () => {
            try {
                console.log('Fetching communities from database...');
                const { data, error } = await supabase
                    .from('communities')
                    .select('id, name')
                    .eq('is_active', true)
                    .order('name', { ascending: true });

                if (error) {
                    console.error('Error fetching communities:', error);
                    throw error;
                }
                console.log('Fetched communities:', data);
                setCommunities(data || []);
            } catch (error) {
                console.error('Error fetching communities:', error);
                setCommunities([]);
            } finally {
                setLoadingCommunities(false);
            }
        };

        fetchCommunities();
    }, []);

    // Pre-fill donor information from user profile
    useEffect(() => {
        if (user && !initialData) {
            setFormData(prev => ({
                ...prev,
                donor_name: user.name || '',
                donor_email: user.email || '',
                donor_phone: user.phone || '',
                donor_city: user.city || '',
                donor_state: user.state || '',
                donor_zip: user.zip_code || '',
            }));
        }
    }, [user, initialData]);
    // Show approval info
    const approvalInfo = (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
            <div className="flex items-start">
                <div className="flex-shrink-0 pt-0.5">
                    <i className="fas fa-info-circle text-blue-500" aria-hidden="true"></i>
                </div>
                <div className="ml-3">
                    <h3 className="text-sm font-medium text-blue-800">Food Donation Approval Required</h3>
                    <div className="mt-2 text-sm text-blue-700">
                        <p>Thank you for your generosity. Every donation goes through an approval process with our small team to ensure the safety of our donors and recipients. This process may take some time. You will receive an update once your donation is approved with instructions on where to bring your donation.</p>
                    </div>
                </div>
            </div>
        </div>
    );

    const [errors, setErrors] = useState({});
    const [imagePreview, setImagePreview] = useState(null);
    const [submitError, setSubmitError] = useState(null);
    const [geocodeTimeout, setGeocodeTimeout] = useState(null);
    // Ref holds the active debounce timer so the cleanup always cancels the
    // most-recently-scheduled call. Using state caused a re-render per keystroke
    // and the cleanup closed over a stale (previous) timer id.
    const geocodeTimerRef = React.useRef(null);

    useEffect(() => {
        if (initialData?.image_url) {
            setImagePreview(initialData.image_url);
        }
    }, [initialData]);

    // Auto-geocode when address changes (with debounce)
    useEffect(() => {
        // Clear any previously scheduled geocode call
        if (geocodeTimerRef.current) {
            clearTimeout(geocodeTimerRef.current);
            geocodeTimerRef.current = null;
        }

        // Only geocode if address exists and coordinates are not already set
        if (formData.full_address && formData.full_address.trim().length > 10 && !formData.latitude && !formData.longitude) {
            geocodeTimerRef.current = setTimeout(() => {
                geocodeTimerRef.current = null;
                geocodeAddress(formData.full_address);
            }, 1500); // 1.5 second delay after user stops typing
        }

        // Cleanup timeout on unmount or before next run
        return () => {
            if (geocodeTimerRef.current) {
                clearTimeout(geocodeTimerRef.current);
                geocodeTimerRef.current = null;
            }
        };
    }, [formData.full_address]);

    // Cleanup function for image preview URL
    useEffect(() => {
        return () => {
            if (imagePreview) {
                URL.revokeObjectURL(imagePreview);
            }
        };
    }, [imagePreview]);

    const handleChange = (e) => {
        const { name, value, type, checked } = e.target;

        // Handle checkbox inputs for dietary tags and allergens
        if (type === 'checkbox' && (name === 'dietary_tags' || name === 'allergens')) {
            setFormData(prev => ({
                ...prev,
                [name]: checked
                    ? [...prev[name], value]
                    : prev[name].filter(item => item !== value)
            }));
        }
        // Handle number inputs
        else if (type === 'number') {
            const numValue = value === '' ? '' : Number(value);
            if (numValue < 0) return; // Prevent negative values
            setFormData(prev => ({
                ...prev,
                [name]: numValue
            }));
        } else {
            setFormData(prev => {
                const next = { ...prev, [name]: value };
                // When the pickup address changes, clear stale geocoded coordinates
                // so the debounce effect will trigger a fresh geocode for the new
                // address. Without this, editing an existing listing and changing
                // the address leaves the old lat/lng in formData forever.
                if (name === 'full_address') {
                    next.latitude = null;
                    next.longitude = null;
                }
                return next;
            });
        }

        // Clear error when field is modified
        if (errors[name]) {
            setErrors(prev => ({
                ...prev,
                [name]: null
            }));
        }
        setSubmitError(null);
    };

    const validateImageFile = (file) => {
        const maxSize = 5 * 1024 * 1024; // 5MB
        const allowedTypes = ['image/jpeg', 'image/png', 'image/gif'];

        if (!allowedTypes.includes(file.type)) {
            return 'Please upload a JPEG, PNG, or GIF image';
        }
        if (file.size > maxSize) {
            return 'Image must be less than 5MB';
        }
        return null;
    };

    const handleImageChange = (e) => {
        const file = e.target.files[0];
        if (file) {
            const error = validateImageFile(file);
            if (error) {
                setErrors(prev => ({
                    ...prev,
                    image: error
                }));
                return;
            }

            // Cleanup old preview
            if (imagePreview) {
                URL.revokeObjectURL(imagePreview);
            }

            const preview = URL.createObjectURL(file);
            setImagePreview(preview);
            setFormData(prev => ({
                ...prev,
                image: file
            }));
            setErrors(prev => ({
                ...prev,
                image: null
            }));
        }
    };

    const geocodeAddress = async (address) => {
        setGeocoding(true);
        console.log('Geocoding address:', address);
        try {
            const MAPBOX_TOKEN = API_CONFIG.MAPBOX.ACCESS_TOKEN;
            const encodedAddress = encodeURIComponent(address);
            const url = `https://api.mapbox.com/geocoding/v5/mapbox.places/${encodedAddress}.json?access_token=${MAPBOX_TOKEN}&limit=1`;
            // Intentionally do NOT log the full URL — it contains the Mapbox token.

            const response = await fetch(url);
            console.log('Geocoding response status:', response.status);
            
            if (!response.ok) {
                const errorText = await response.text();
                console.error('Geocoding API error:', response.status, errorText);
                throw new Error(`Geocoding failed: ${response.status}`);
            }
            
            const data = await response.json();
            console.log('Geocoding data:', data);
            
            if (data.features && data.features.length > 0) {
                const [longitude, latitude] = data.features[0].center;
                console.log('Found coordinates:', { latitude, longitude });
                setFormData(prev => ({
                    ...prev,
                    latitude,
                    longitude
                }));
                setErrors(prev => ({
                    ...prev,
                    full_address: null
                }));
                return { success: true, latitude, longitude };
            } else {
                console.warn('No geocoding results found for address:', address);
                setErrors(prev => ({
                    ...prev,
                    full_address: 'Address not found. Please check and try again.'
                }));
                return { success: false };
            }
        } catch (error) {
            console.error('Geocoding error:', error);
            setErrors(prev => ({
                ...prev,
                full_address: 'Failed to locate address. Please try again.'
            }));
            return { success: false };
        } finally {
            setGeocoding(false);
        }
    };

    const handleAddressBlur = async () => {
        if (formData.full_address && formData.full_address.trim() && !formData.latitude && !formData.longitude) {
            console.log('Address blur - triggering geocoding');
            await geocodeAddress(formData.full_address);
        }
    };

    const validateForm = () => {
        const newErrors = {};
        if (!formData.title) newErrors.title = 'Title is required';
        if (!formData.quantity || Number(formData.quantity) < 1) newErrors.quantity = 'Quantity must be at least 1';
        if (!formData.category) newErrors.category = 'Category is required';
        // Expiry date required only if not produce
        if (formData.category !== 'produce' && !formData.expiry_date) newErrors.expiry_date = 'Expiry date is required';
        if (formData.expiry_date) {
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            const expiry = new Date(formData.expiry_date + 'T00:00:00');
            if (expiry < today) newErrors.expiry_date = 'Expiry date cannot be in the past';
        }
        if (!formData.donor_type) newErrors.donor_type = 'Please select donor type';
        if (!formData.donor_name) newErrors.donor_name = 'Name/Organization is required';
        if (!formData.donor_zip) newErrors.donor_zip = 'ZIP code is required';
        if (!formData.donor_city) newErrors.donor_city = 'City is required';
        if (!formData.donor_state) newErrors.donor_state = 'State is required';
        if (!formData.donor_email && !formData.donor_phone) newErrors.donor_email = 'Email or phone is required';
        if (!formData.donor_occupation) newErrors.donor_occupation = 'Occupation is required';
        if (!formData.full_address) newErrors.full_address = 'Full address is required for map location';
        // Only require geocoding if address is provided and geocoding is not in progress
        if (formData.full_address && (!formData.latitude || !formData.longitude) && !geocoding) {
            newErrors.full_address = 'Address geocoding failed. Please verify the address is correct.';
        }
        if (!formData.image && !initialData?.image_url) {
            newErrors.image = 'Photo is required';
        }
        // Prevent stock photo uploads (simple check: filename contains 'stock')
        if (formData.image && formData.image.name && /stock/i.test(formData.image.name)) {
            newErrors.image = 'Stock photos are not allowed. Please upload a real photo of the food.';
        }
        setErrors(newErrors);
        
        // If there are errors, scroll to and focus on the first error field
        if (Object.keys(newErrors).length > 0) {
            const firstErrorField = Object.keys(newErrors)[0];
            // Use setTimeout to ensure DOM has updated with error messages
            setTimeout(() => {
                const fieldElement = document.querySelector(`[name="${firstErrorField}"]`);
                if (fieldElement) {
                    // Scroll to the field with some offset
                    const elementPosition = fieldElement.getBoundingClientRect().top + window.pageYOffset;
                    const offsetPosition = elementPosition - 100; // 100px offset from top
                    
                    window.scrollTo({
                        top: offsetPosition,
                        behavior: 'smooth'
                    });
                    
                    // Focus on the field
                    fieldElement.focus();
                }
            }, 100);
        }
        
        return Object.keys(newErrors).length === 0;
    }

    const handleSubmit = async (e) => {
        e.preventDefault();
        setSubmitError(null);

        if (validateForm()) {
            try {
                // Set status to pending
                await onSubmit({ ...formData, status: 'pending' });
            } catch (error) {
                console.error('Form submission error:', error);
                setSubmitError('Failed to submit listing. Please try again.');
            }
        }
    };

    return (
        <form 
            data-name="food-form" 
            onSubmit={handleSubmit} 
            className="space-y-6"
            aria-label="Food listing form"
            noValidate
        >
            {approvalInfo}
            {submitError && (
                <div 
                    className="bg-red-50 border border-red-200 rounded-lg p-4" 
                    role="alert"
                >
                    <p className="text-red-700">
                        <i className="fas fa-exclamation-circle mr-2"></i>
                        {submitError}
                    </p>
                </div>
            )}

            {/* Donor Info Section - Top of Form */}
            <div className="mb-8 p-6 bg-primary-50 rounded-xl border border-primary-200">
                <h2 className="text-xl font-bold text-primary-700 mb-4">Donor Information</h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <Input
                        label="Name / Organization"
                        name="donor_name"
                        value={formData.donor_name}
                        onChange={handleChange}
                        error={errors.donor_name}
                        required
                        maxLength={100}
                        helperText="Enter your full name or organization name."
                    />
                    <Input
                        label="ZIP Code"
                        name="donor_zip"
                        value={formData.donor_zip}
                        onChange={handleChange}
                        error={errors.donor_zip}
                        required
                        maxLength={10}
                        helperText="Enter your ZIP code."
                    />
                    <Input
                        label="City"
                        name="donor_city"
                        value={formData.donor_city}
                        onChange={handleChange}
                        error={errors.donor_city}
                        required
                        maxLength={50}
                        helperText="Enter your city."
                    />
                    <Input
                        label="State"
                        name="donor_state"
                        type="select"
                        value={formData.donor_state}
                        onChange={handleChange}
                        error={errors.donor_state}
                        required
                        helperText="Select your state."
                        options={[
                            { value: '', label: 'Select State' },
                            { value: 'AL', label: 'Alabama' },
                            { value: 'AK', label: 'Alaska' },
                            { value: 'AZ', label: 'Arizona' },
                            { value: 'AR', label: 'Arkansas' },
                            { value: 'CA', label: 'California' },
                            { value: 'CO', label: 'Colorado' },
                            { value: 'CT', label: 'Connecticut' },
                            { value: 'DE', label: 'Delaware' },
                            { value: 'FL', label: 'Florida' },
                            { value: 'GA', label: 'Georgia' },
                            { value: 'HI', label: 'Hawaii' },
                            { value: 'ID', label: 'Idaho' },
                            { value: 'IL', label: 'Illinois' },
                            { value: 'IN', label: 'Indiana' },
                            { value: 'IA', label: 'Iowa' },
                            { value: 'KS', label: 'Kansas' },
                            { value: 'KY', label: 'Kentucky' },
                            { value: 'LA', label: 'Louisiana' },
                            { value: 'ME', label: 'Maine' },
                            { value: 'MD', label: 'Maryland' },
                            { value: 'MA', label: 'Massachusetts' },
                            { value: 'MI', label: 'Michigan' },
                            { value: 'MN', label: 'Minnesota' },
                            { value: 'MS', label: 'Mississippi' },
                            { value: 'MO', label: 'Missouri' },
                            { value: 'MT', label: 'Montana' },
                            { value: 'NE', label: 'Nebraska' },
                            { value: 'NV', label: 'Nevada' },
                            { value: 'NH', label: 'New Hampshire' },
                            { value: 'NJ', label: 'New Jersey' },
                            { value: 'NM', label: 'New Mexico' },
                            { value: 'NY', label: 'New York' },
                            { value: 'NC', label: 'North Carolina' },
                            { value: 'ND', label: 'North Dakota' },
                            { value: 'OH', label: 'Ohio' },
                            { value: 'OK', label: 'Oklahoma' },
                            { value: 'OR', label: 'Oregon' },
                            { value: 'PA', label: 'Pennsylvania' },
                            { value: 'RI', label: 'Rhode Island' },
                            { value: 'SC', label: 'South Carolina' },
                            { value: 'SD', label: 'South Dakota' },
                            { value: 'TN', label: 'Tennessee' },
                            { value: 'TX', label: 'Texas' },
                            { value: 'UT', label: 'Utah' },
                            { value: 'VT', label: 'Vermont' },
                            { value: 'VA', label: 'Virginia' },
                            { value: 'WA', label: 'Washington' },
                            { value: 'WV', label: 'West Virginia' },
                            { value: 'WI', label: 'Wisconsin' },
                            { value: 'WY', label: 'Wyoming' },
                            { value: 'DC', label: 'District of Columbia' }
                        ]}
                    />
                    <Input
                        label="Active Communities"
                        name="school_district"
                        type="select"
                        value={formData.school_district}
                        onChange={handleChange}
                        error={errors.school_district}
                        disabled={loadingCommunities}
                        options={[
                            { value: '', label: loadingCommunities ? 'Loading communities...' : 'Select Community' },
                            ...communities.map(community => ({
                                value: community.name,
                                label: community.name
                            }))
                        ]}
                        helperText="choose a community"
                    />
                    <Input
                        label="Email"
                        name="donor_email"
                        type="email"
                        value={formData.donor_email}
                        onChange={handleChange}
                        error={errors.donor_email}
                        maxLength={100}
                        helperText="Enter your email address."
                    />
                    <Input
                        label="Phone"
                        name="donor_phone"
                        type="tel"
                        value={formData.donor_phone}
                        onChange={handleChange}
                        error={errors.donor_phone}
                        maxLength={20}
                        helperText="Enter your phone number."
                    />
                </div>
                <div className="mt-6">
                    <div className="relative">
                        <Input
                            label="Full Address (for map location)"
                            name="full_address"
                            value={formData.full_address}
                            onChange={handleChange}
                            onBlur={handleAddressBlur}
                            error={errors.full_address}
                            placeholder="e.g., 123 Main St, San Francisco, CA 94102"
                            helperText="Enter the complete pickup address. We'll automatically locate it on the map."
                        />
                        {geocoding && (
                            <div className="absolute right-3 top-9">
                                <i className="fas fa-spinner fa-spin text-[#2CABE3]"></i>
                            </div>
                        )}
                        {formData.latitude && formData.longitude && (
                            <div className="mt-2 text-sm text-primary-600 flex items-center">
                                <i className="fas fa-check-circle mr-2"></i>
                                Location verified: {formData.latitude.toFixed(4)}, {formData.longitude.toFixed(4)}
                            </div>
                        )}
                        {errors.full_address && formData.full_address && !geocoding && (
                            <button
                                type="button"
                                onClick={() => geocodeAddress(formData.full_address)}
                                className="mt-2 text-sm text-[#2CABE3] hover:underline flex items-center"
                            >
                                <i className="fas fa-redo mr-1"></i>
                                Retry address verification
                            </button>
                        )}
                    </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-6">
                    <Input
                        label="Occupation / Role"
                        name="donor_occupation"
                        value={formData.donor_occupation}
                        onChange={handleChange}
                        error={errors.donor_occupation}
                        required
                        maxLength={100}
                        helperText="Your occupation or role in the organization."
                    />
                    <Input
                    label="Donor Type"
                    name="donor_type"
                    type="select"
                    value={formData.donor_type}
                    onChange={handleChange}
                    error={errors.donor_type}
                    required
                    options={[
                        { value: '', label: 'Select type' },
                        { value: 'individual', label: 'Individual/Family' },
                        { value: 'organization', label: 'Organization' }
                    ]}
                    aria-describedby="donor_type-error"
                />
                    
                </div>
            </div>
            {/* ...existing code... */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              
                <Input
                    label="What are you donating?"
                    name="title"
                    value={formData.title}
                    onChange={handleChange}
                    error={errors.title}
                    required
                    maxLength={100}
                    aria-describedby="title-error"
                    helperText="Enter a short, clear name for the food item."
                />

                <Input
                    label="Category"
                    name="category"
                    type="select"
                    value={formData.category}
                    onChange={handleChange}
                    error={errors.category}
                    required
                    options={[
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
                        { value: 'prepared', label: 'Prepared Foods' }
                    ]}
                    aria-describedby="category-error"
                    helperText="Select the type of food you are donating."
                />

                <div className="md:col-span-2">
                    <Input
                        label="Description"
                        name="description"
                        type="textarea"
                        value={formData.description}
                        onChange={handleChange}
                        error={errors.description}
                        required
                        maxLength={500}
                        placeholder="Example: Fresh organic apples from my backyard tree. Crisp and sweet, perfect for eating fresh or baking. Picked this morning."
                        aria-describedby="description-error"
                        helperText="Describe the food item, its condition, source, and any special details recipients should know."
                    />
                </div>

                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                        Quantity <span className="text-red-500">*</span>
                    </label>
                    <div className="flex gap-2">
                        <div className="flex-1">
                            <input
                                type="number"
                                name="quantity"
                                value={formData.quantity}
                                onChange={handleChange}
                                min="0"
                                step="0.01"
                                required
                                className={`w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent ${
                                    errors.quantity ? 'border-red-500' : 'border-gray-300'
                                }`}
                                placeholder="Enter amount"
                                aria-describedby="quantity-error"
                            />
                        </div>
                        <div className="w-40">
                            <select
                                name="unit"
                                value={formData.unit}
                                onChange={handleChange}
                                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                            >
                                <option value="lb">Pounds (lb)</option>
                                <option value="oz">Ounces (oz)</option>
                                <option value="kg">Kilograms (kg)</option>
                                <option value="g">Grams (g)</option>
                                <option value="count">Count/Items</option>
                                <option value="serving">Servings</option>
                            </select>
                        </div>
                    </div>
                    {errors.quantity && (
                        <p className="mt-1 text-sm text-red-500" id="quantity-error">
                            {errors.quantity}
                        </p>
                    )}
                    <p className="mt-1 text-sm text-gray-500">Enter the quantity and select the unit.</p>
                </div>

                {formData.category !== 'produce' && (
                    <Input
                        label="Expiration Date"
                        name="expiry_date"
                        type="date"
                        value={formData.expiry_date}
                        onChange={handleChange}
                        error={errors.expiry_date}
                        min={(() => { const _d = new Date(); return [_d.getFullYear(), String(_d.getMonth()+1).padStart(2,'0'), String(_d.getDate()).padStart(2,'0')].join('-'); })()}
                        aria-describedby="expiry_date-error"
                        helperText="Required for all except produce."
                    />
                )}

                <Input
                    label="Pickup Deadline (Optional)"
                    name="pickup_by"
                    type="datetime-local"
                    value={formData.pickup_by}
                    onChange={handleChange}
                    error={errors.pickup_by}
                    min={(() => { const _d = new Date(); return `${[_d.getFullYear(), String(_d.getMonth()+1).padStart(2,'0'), String(_d.getDate()).padStart(2,'0')].join('-')}T${String(_d.getHours()).padStart(2,'0')}:${String(_d.getMinutes()).padStart(2,'0')}`; })()}
                    aria-describedby="pickup_by-error"
                    helperText="Set a specific time when food must be picked up by. Creates urgency for recipients!"
                />

                {/* Dietary Tags */}
                <div className="md:col-span-2">
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                        Dietary Information (Optional)
                    </label>
                    <p className="text-sm text-gray-500 mb-3">Select all that apply to help recipients find suitable food</p>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        {[
                            { value: 'vegetarian', label: 'Vegetarian', icon: '🥬' },
                            { value: 'vegan', label: 'Vegan', icon: '🌱' },
                            { value: 'gluten-free', label: 'Gluten-Free', icon: '🌾' },
                            { value: 'dairy-free', label: 'Dairy-Free', icon: '🥛' },
                            { value: 'nut-free', label: 'Nut-Free', icon: '🥜' },
                            { value: 'halal', label: 'Halal', icon: '☪️' },
                            { value: 'kosher', label: 'Kosher', icon: '✡️' },
                            { value: 'organic', label: 'Organic', icon: '♻️' }
                        ].map(tag => (
                            <label key={tag.value} className="flex items-center space-x-2 cursor-pointer">
                                <input
                                    type="checkbox"
                                    name="dietary_tags"
                                    value={tag.value}
                                    checked={formData.dietary_tags.includes(tag.value)}
                                    onChange={handleChange}
                                    className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                                />
                                <span className="text-sm text-gray-700">
                                    {tag.icon} {tag.label}
                                </span>
                            </label>
                        ))}
                    </div>
                </div>

                {/* Allergens */}
                <div className="md:col-span-2">
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                        Contains Allergens (Optional)
                    </label>
                    <p className="text-sm text-gray-500 mb-3">Select all allergens present in the food</p>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        {[
                            { value: 'milk', label: 'Milk' },
                            { value: 'eggs', label: 'Eggs' },
                            { value: 'fish', label: 'Fish' },
                            { value: 'shellfish', label: 'Shellfish' },
                            { value: 'tree-nuts', label: 'Tree Nuts' },
                            { value: 'peanuts', label: 'Peanuts' },
                            { value: 'wheat', label: 'Wheat' },
                            { value: 'soy', label: 'Soy' }
                        ].map(allergen => (
                            <label key={allergen.value} className="flex items-center space-x-2 cursor-pointer">
                                <input
                                    type="checkbox"
                                    name="allergens"
                                    value={allergen.value}
                                    checked={formData.allergens.includes(allergen.value)}
                                    onChange={handleChange}
                                    className="w-4 h-4 text-orange-600 border-gray-300 rounded focus:ring-orange-500"
                                />
                                <span className="text-sm text-gray-700">{allergen.label}</span>
                            </label>
                        ))}
                    </div>
                </div>

                {/* Ingredients */}
                <div className="md:col-span-2">
                    <Input
                        label="Ingredients List (Optional)"
                        name="ingredients"
                        type="textarea"
                        value={formData.ingredients}
                        onChange={handleChange}
                        error={errors.ingredients}
                        maxLength={500}
                        placeholder="List main ingredients if applicable (e.g., flour, sugar, eggs, butter)"
                        aria-describedby="ingredients-error"
                        helperText="Help recipients know exactly what's in the food"
                    />
                </div>

                {/* Location field removed */}

                <div className="md:col-span-2">
                    <Input
                        label="Photo"
                        name="image"
                        type="file"
                        onChange={handleImageChange}
                        accept="image/jpeg,image/png,image/gif"
                        error={errors.image}
                        required
                        aria-describedby="image-error"
                        helperText="Upload a real photo of the food. No stock images allowed."
                    />
                    {imagePreview && (
                        <div className="mt-2">
                            <img 
                                src={imagePreview} 
                                alt="Food item preview" 
                                className="h-32 w-32 object-cover rounded-lg border border-primary-200 shadow-sm"
                            />
                        </div>
                    )}
                    {initialData?.image_url && !imagePreview && (
                        <div className="mt-2">
                            <img 
                                src={initialData.image_url} 
                                alt="Current food item" 
                                className="h-32 w-32 object-cover rounded-lg border border-primary-200 shadow-sm"
                            />
                        </div>
                    )}
                </div>

                {/* Listing Type field removed */}
            </div>

            <div className="flex justify-end space-x-4">
                <Button
                    type="button"
                    variant="secondary"
                    onClick={() => window.history.back()}
                    aria-label="Cancel and return to previous page"
                >
                    Cancel
                </Button>
                <Button
                    type="submit"
                    disabled={loading}
                    aria-label={loading ? 'Submitting form...' : 'Submit listing'}
                >
                    {loading ? (
                        <div className="flex items-center">
                            <i className="fas fa-spinner fa-spin mr-2" aria-hidden="true"></i>
                            Submitting...
                        </div>
                    ) : (
                        'Submit Listing'
                    )}
                </Button>
            </div>
        </form>
    );
}

FoodForm.propTypes = {
    initialData: PropTypes.shape({
        title: PropTypes.string,
        description: PropTypes.string,
        quantity: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
        unit: PropTypes.string,
        category: PropTypes.string,
        expiry_date: PropTypes.string,
    // ...existing code...
        image: PropTypes.instanceOf(File)
    }),
    onSubmit: PropTypes.func.isRequired,
    loading: PropTypes.bool
};

export default FoodForm;
