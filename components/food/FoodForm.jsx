import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import Input from '../common/Input';
import Button from '../common/Button';

function FoodForm({
    initialData = null,
    onSubmit,
    loading = false
}) {
    const [formData, setFormData] = useState({
        title: '',
        description: '',
        quantity: '',
        unit: 'lb', // Only pounds allowed
        category: '',
        expiry_date: '',
        donor_type: '', // 'individual' or 'organization'
        donor_zip: '',
        donor_city: '',
        donor_state: '',
    school_district: '',
        latitude: null,
        longitude: null,
        image: null,
        status: 'pending',
        ...initialData
    });
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
                        <p>Only approved families and organizations can donate food. Each submission will be reviewed and must be approved before the donation is listed.</p>
                    </div>
                </div>
            </div>
        </div>
    );

    const [errors, setErrors] = useState({});
    const [imagePreview, setImagePreview] = useState(null);
    const [submitError, setSubmitError] = useState(null);

    useEffect(() => {
        if (initialData?.image_url) {
            setImagePreview(initialData.image_url);
        }
    }, [initialData]);

    // Cleanup function for image preview URL
    useEffect(() => {
        return () => {
            if (imagePreview) {
                URL.revokeObjectURL(imagePreview);
            }
        };
    }, [imagePreview]);

    const handleChange = (e) => {
        const { name, value, type } = e.target;
        
        // Handle number inputs
        if (type === 'number') {
            const numValue = value === '' ? '' : Number(value);
            if (numValue < 0) return; // Prevent negative values
            setFormData(prev => ({
                ...prev,
                [name]: numValue
            }));
        } else {
            setFormData(prev => ({
                ...prev,
                [name]: value
            }));
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

    const validateForm = () => {
        const newErrors = {};
        if (!formData.title) newErrors.title = 'Title is required';
        if (!formData.quantity) newErrors.quantity = 'Quantity is required';
        if (!formData.category) newErrors.category = 'Category is required';
        // Expiry date required only if not produce
        if (formData.category !== 'produce' && !formData.expiry_date) newErrors.expiry_date = 'Expiry date is required';
        if (!formData.donor_type) newErrors.donor_type = 'Please select donor type';
        if (!formData.donor_name) newErrors.donor_name = 'Name/Organization is required';
        if (!formData.donor_zip) newErrors.donor_zip = 'ZIP code is required';
        if (!formData.donor_city) newErrors.donor_city = 'City is required';
        if (!formData.donor_state) newErrors.donor_state = 'State is required';
        if (!formData.donor_email && !formData.donor_phone) newErrors.donor_email = 'Email or phone is required';
        if (!formData.donor_occupation) newErrors.donor_occupation = 'Occupation is required';
        if (!formData.image && !initialData?.image_url) {
            newErrors.image = 'Photo is required';
        }
        // Prevent stock photo uploads (simple check: filename contains 'stock')
        if (formData.image && formData.image.name && /stock/i.test(formData.image.name)) {
            newErrors.image = 'Stock photos are not allowed. Please upload a real photo of the food.';
        }
        setErrors(newErrors);
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
            <div className="mb-8 p-6 bg-green-50 rounded-xl border border-green-200">
                <h2 className="text-xl font-bold text-green-700 mb-4">Donor Information</h2>
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
                        value={formData.donor_state}
                        onChange={handleChange}
                        error={errors.donor_state}
                        required
                        maxLength={50}
                        helperText="Enter your state."
                    />
                    <Input
                        label="School District"
                        name="school_district"
                        type="select"
                        value={formData.school_district}
                        onChange={handleChange}
                        error={errors.school_district}
                        options={[
                            { value: '', label: 'Select school district' },
                            { value: 'Do Good Warehouse', label: 'Do Good Warehouse' },
                            { value: 'Ruby Bridges Elementary CC', label: 'Ruby Bridges Elementary CC' },
                            { value: 'NEA/ACLC CC', label: 'NEA/ACLC CC' },
                            { value: 'Academy of Alameda CC', label: 'Academy of Alameda CC' },
                            { value: 'Island HS CC', label: 'Island HS CC' },
                            { value: 'Encinal Jr Sr High School', label: 'Encinal Jr Sr High School' }
                        ]}
                        helperText="If this donation is for a school, choose the district or school."
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
                    <Input
                        label="Occupation"
                        name="donor_occupation"
                        value={formData.donor_occupation}
                        onChange={handleChange}
                        error={errors.donor_occupation}
                        required
                        maxLength={100}
                        helperText="Enter your occupation."
                    />
                </div>
            </div>
            {/* ...existing code... */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
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
                <Input
                    label="Title"
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
                        aria-describedby="description-error"
                    />
                </div>

                <Input
                    label="Quantity (LB Only)"
                    name="quantity"
                    type="number"
                    value={formData.quantity}
                    onChange={handleChange}
                    error={errors.quantity}
                    required
                    min="0"
                    step="0.01"
                    aria-describedby="quantity-error"
                    helperText="Enter the weight in pounds (LB) only."
                />

                {/* Unit is always LB, so no unit selector needed */}

                {formData.category !== 'produce' && (
                    <Input
                        label="Expiration Date"
                        name="expiry_date"
                        type="date"
                        value={formData.expiry_date}
                        onChange={handleChange}
                        error={errors.expiry_date}
                        min={new Date().toISOString().split('T')[0]}
                        aria-describedby="expiry_date-error"
                        helperText="Required for all except produce."
                    />
                )}

                {/* Location field removed */}

                <div className="md:col-span-2">
                    <Input
                        label="Photo"
                        name="image"
                        type="file"
                        onChange={handleImageChange}
                        accept="image/jpeg,image/png,image/gif"
                        error={errors.image}
                        aria-describedby="image-error"
                        helperText="Upload a real photo of the food. No stock images allowed."
                    />
                    {imagePreview && (
                        <div className="mt-2">
                            <img 
                                src={imagePreview} 
                                alt="Food item preview" 
                                className="h-32 w-32 object-cover rounded-lg border border-green-200 shadow-sm"
                            />
                        </div>
                    )}
                    {initialData?.image_url && !imagePreview && (
                        <div className="mt-2">
                            <img 
                                src={initialData.image_url} 
                                alt="Current food item" 
                                className="h-32 w-32 object-cover rounded-lg border border-green-200 shadow-sm"
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
