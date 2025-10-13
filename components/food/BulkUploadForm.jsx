import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import Input from '../common/Input';
import Button from '../common/Button';
import { reportError, safeDownload } from '../../utils/helpers';

function BulkUploadForm({
    initialData = null,
    onSubmit,
    loading = false
}) {
    const [formData, setFormData] = useState({
        csvFile: null,
        imageFiles: [],
        location: '',
        notes: '',
        defaultType: 'donation', // 'donation' or 'trade'
        ...initialData
    });

    const [errors, setErrors] = useState({});
    const [previewItems, setPreviewItems] = useState([]);
    const [isProcessing, setIsProcessing] = useState(false);
    const [imagePreviews, setImagePreviews] = useState([]);

    const csvTemplate = `title,description,quantity,unit,category,expiryDate
Fresh Apples,Organic Red Delicious,5,kg,produce,2025-08-13
Whole Wheat Bread,Freshly Baked,2,loaf,bakery,
Milk,Organic Whole Milk,1,gallon,dairy,2025-08-08`;

    // Function to download CSV template
    const handleDownloadTemplate = () => {
        safeDownload(csvTemplate, 'food-listing-template.csv', 'text/csv');
    };

    // Cleanup function for file URLs
    useEffect(() => {
        return () => {
            if (formData.imageFiles.length > 0) {
                formData.imageFiles.forEach(file => {
                    if (file.preview) {
                        URL.revokeObjectURL(file.preview);
                    }
                });
            }
        };
    }, [formData.imageFiles]);

    const validateImageFiles = (files) => {
        const maxFileSize = 5 * 1024 * 1024; // 5MB
        const allowedTypes = ['image/jpeg', 'image/png', 'image/gif'];
        
        for (const file of files) {
            if (!allowedTypes.includes(file.type)) {
                return 'Only JPEG, PNG, and GIF images are allowed';
            }
            if (file.size > maxFileSize) {
                return 'Each image must be less than 5MB';
            }
        }
        return null;
    };

    const handleChange = (e) => {
        const { name, value, type, files } = e.target;
        
        if (type === 'file' && name === 'csvFile') {
            const file = files[0];
            if (file) {
                if (!file.type.includes('csv')) {
                    setErrors(prev => ({
                        ...prev,
                        csvFile: 'Please upload a valid CSV file'
                    }));
                    return;
                }
                setFormData(prev => ({
                    ...prev,
                    csvFile: file
                }));
                
                setIsProcessing(true);
                // Process CSV preview
                const reader = new FileReader();
                reader.onload = (event) => {
                    try {
                        const csvData = parseCsv(event.target.result);
                        if (csvData.length === 0) {
                            throw new Error('CSV file is empty');
                        }
                        setPreviewItems(csvData.slice(0, 3)); // Show first 3 items as preview
                        setIsProcessing(false);
                    } catch (error) {
                        console.error('CSV parsing error:', error);
                        setErrors(prev => ({
                            ...prev,
                            csvFile: error.message || 'Invalid CSV format. Please check the template.'
                        }));
                        setIsProcessing(false);
                    }
                };
                reader.onerror = () => {
                    setErrors(prev => ({
                        ...prev,
                        csvFile: 'Failed to read the CSV file. Please try again.'
                    }));
                    setIsProcessing(false);
                };
                reader.readAsText(file);
            }
        } else if (type === 'file' && name === 'imageFiles') {
            const selectedFiles = Array.from(files);
            const imageError = validateImageFiles(selectedFiles);
            
            if (imageError) {
                setErrors(prev => ({
                    ...prev,
                    imageFiles: imageError
                }));
                return;
            }
            
            // Create preview URLs for images
            const filesWithPreviews = selectedFiles.map(file => {
                const preview = URL.createObjectURL(file);
                return Object.assign(file, { preview });
            });
            
            setFormData(prev => ({
                ...prev,
                imageFiles: filesWithPreviews
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
    };

    const validateForm = () => {
        const newErrors = {};
        if (!formData.csvFile) {
            newErrors.csvFile = 'CSV file is required';
        }
        if (!formData.location.trim()) {
            newErrors.location = 'Location is required';
        }
        if (formData.imageFiles.length > 10) {
            newErrors.imageFiles = 'Maximum 10 images allowed';
        }
        
        setErrors(newErrors);
        return Object.keys(newErrors).length === 0;
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        
        if (validateForm()) {
            try {
                const reader = new FileReader();
                reader.onload = async (event) => {
                    try {
                        const csvData = parseCsv(event.target.result);
                        const itemsWithImages = csvData.map((item, index) => {
                            // Distribute images evenly across items
                            const imageFile = formData.imageFiles.length > 0 
                                ? formData.imageFiles[index % formData.imageFiles.length] 
                                : null;
                            return {
                                ...item,
                                imageFile
                            };
                        });

                        await onSubmit({
                            ...formData,
                            items: itemsWithImages
                        });
                    } catch (error) {
                        console.error('CSV processing error:', error);
                        setErrors(prev => ({
                            ...prev,
                            submit: error.message || 'Failed to process CSV data.'
                        }));
                    }
                };
                reader.readAsText(formData.csvFile);
            } catch (error) {
                console.error('Form submission error:', error);
                setErrors(prev => ({
                    ...prev,
                    submit: 'Failed to submit form. Please try again.'
                }));
            }
        }
    };

    // Improved CSV parser with better validation
    const parseCsv = (csvText) => {
        const lines = csvText.split('\n');
        if (lines.length < 2) {
            throw new Error('CSV must contain headers and at least one data row');
        }

        const requiredHeaders = ['title', 'description', 'quantity', 'unit', 'category'];
        const optionalHeaders = ['expiryDate'];
        const headers = lines[0].split(',').map(h => h.trim().toLowerCase());
        
        // Validate required headers
        const missingHeaders = requiredHeaders.filter(h => !headers.includes(h));
        if (missingHeaders.length > 0) {
            throw new Error(`Missing required headers: ${missingHeaders.join(', ')}`);
        }

        return lines.slice(1)
            .filter(line => line.trim().length > 0)
            .map((line, index) => {
                const values = line.split(',').map(v => v.trim());
                
                // Validate row length
                if (values.length !== headers.length) {
                    throw new Error(`Row ${index + 2} has incorrect number of columns`);
                }

                const item = {};
                headers.forEach((header, index) => {
                    if (header === 'expiryDate' && (!values[index] || values[index] === '')) {
                        // Set default expiry date to 7 days from now
                        const defaultDate = new Date();
                        defaultDate.setDate(defaultDate.getDate() + 7);
                        item[header] = defaultDate.toISOString().split('T')[0];
                    } else {
                        item[header] = values[index] || '';
                    }
                });

                // Validate required fields
                if (!item.title) {
                    throw new Error(`Row ${index + 2}: Title is required`);
                }
                if (!item.quantity || isNaN(item.quantity)) {
                    throw new Error(`Row ${index + 2}: Quantity must be a number`);
                }
                if (!item.unit) {
                    throw new Error(`Row ${index + 2}: Unit is required`);
                }
                
                // Validate date format
                const dateRegex = /^\d{4}-\d{2}-\d{2}$/;
                if (item.expiryDate && !dateRegex.test(item.expiryDate)) {
                    throw new Error(`Row ${index + 2}: Invalid date format. Use YYYY-MM-DD`);
                }

                return item;
            });
    };

    const downloadTemplate = () => {
        const csvContent = [
            'title,description,quantity,unit,expiryDate,category',
            'Organic Apples,Fresh locally grown apples,5,kg,2023-12-31,produce',
            'Sourdough Bread,Freshly baked this morning,2,loaves,2023-12-25,bakery'
        ].join('\n');

        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        safeDownload(blob, 'food_listings_template.csv');
    };

    return (
        <form 
            data-name="bulk-upload-form" 
            onSubmit={handleSubmit} 
            className="space-y-6"
            aria-label="Bulk food items upload form"
            noValidate
        >
            {errors.submit && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                    <div className="flex">
                        <div className="flex-shrink-0">
                            <i className="fas fa-exclamation-circle text-red-400"></i>
                        </div>
                        <div className="ml-3">
                            <p className="text-sm text-red-700">{errors.submit}</p>
                        </div>
                    </div>
                </div>
            )}
            <div className="bg-blue-50 rounded-lg p-4 mb-6">
                <div className="flex items-start">
                    <div className="flex-shrink-0 pt-0.5">
                        <i className="fas fa-info-circle text-blue-500"></i>
                    </div>
                    <div className="ml-3">
                        <h3 className="text-sm font-medium text-blue-800">Bulk Upload Instructions</h3>
                        <div className="mt-2 text-sm text-blue-700">
                            <p>Upload multiple food items at once using our CSV template. All items will share the same location and listing type.</p>
                            <button 
                                type="button"
                                onClick={downloadTemplate}
                                className="mt-2 text-blue-600 hover:text-blue-800 font-medium flex items-center"
                            >
                                <i className="fas fa-download mr-1"></i>
                                Download CSV Template
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="md:col-span-2">
                    <Input
                        label="CSV File with Food Items"
                        name="csvFile"
                        type="file"
                        onChange={handleChange}
                        accept=".csv"
                        error={errors.csvFile}
                        required
                    />
                </div>

                <div className="md:col-span-2">
                    <Input
                        label="Bulk Images (Optional)"
                        name="imageFiles"
                        type="file"
                        onChange={handleChange}
                        accept="image/*"
                        multiple
                        helperText="You can upload multiple images that will be distributed across your listings"
                    />
                </div>

                <Input
                    label="Listing Type"
                    name="defaultType"
                    type="select"
                    value={formData.defaultType}
                    onChange={handleChange}
                    options={[
                        { value: 'donation', label: 'Donation' },
                        { value: 'trade', label: 'Trade' }
                    ]}
                />

                <Input
                    label="Location"
                    name="location"
                    value={formData.location}
                    onChange={handleChange}
                    error={errors.location}
                    required
                    icon={<i className="fas fa-map-marker-alt"></i>}
                />

                <div className="md:col-span-2">
                    <Input
                        label="Additional Notes"
                        name="notes"
                        type="textarea"
                        value={formData.notes}
                        onChange={handleChange}
                        placeholder="Any additional information about this batch of items"
                    />
                </div>

                {imagePreviews.length > 0 && (
                    <div className="md:col-span-2">
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                            Image Previews
                        </label>
                        <div className="grid grid-cols-4 gap-4">
                            {imagePreviews.map((preview, index) => (
                                <div key={index} className="relative">
                                    <img
                                        src={preview}
                                        alt={`Preview ${index + 1}`}
                                        className="h-24 w-24 object-cover rounded-lg"
                                    />
                                    <button
                                        type="button"
                                        className="absolute -top-2 -right-2 bg-red-500 text-white rounded-full p-1 hover:bg-red-600"
                                        onClick={() => {
                                            // Remove the image
                                            const newImageFiles = formData.imageFiles.filter((_, i) => i !== index);
                                            const newPreviews = imagePreviews.filter((_, i) => i !== index);
                                            setFormData(prev => ({ ...prev, imageFiles: newImageFiles }));
                                            setImagePreviews(newPreviews);
                                            URL.revokeObjectURL(preview);
                                        }}
                                    >
                                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                                            <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                                        </svg>
                                    </button>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </div>

            {isProcessing && (
                <div className="text-center py-4">
                    <div className="inline-flex items-center">
                        <i className="fas fa-spinner fa-spin mr-2"></i>
                        <span>Processing CSV file...</span>
                    </div>
                </div>
            )}

            {previewItems.length > 0 && (
                <div className="border rounded-lg overflow-hidden">
                    <div className="bg-gray-50 px-4 py-3 border-b">
                        <h3 className="text-sm font-medium text-gray-700">CSV Preview (First 3 Items)</h3>
                    </div>
                    <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200">
                            <thead className="bg-gray-50">
                                <tr>
                                    {[...Object.keys(previewItems[0]), 'Image'].map((header, index) => (
                                        <th 
                                            key={index}
                                            className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                                        >
                                            {header}
                                        </th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody className="bg-white divide-y divide-gray-200">
                                {previewItems.map((item, rowIndex) => (
                                    <tr key={rowIndex}>
                                        {Object.values(item).map((value, cellIndex) => (
                                            <td 
                                                key={cellIndex}
                                                className="px-6 py-4 whitespace-nowrap text-sm text-gray-500"
                                            >
                                                {value}
                                            </td>
                                        ))}
                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                            {formData.imageFiles.length > 0 && (
                                                <img
                                                    src={formData.imageFiles[rowIndex % formData.imageFiles.length].preview}
                                                    alt={`Preview for ${item.title}`}
                                                    className="h-12 w-12 object-cover rounded"
                                                />
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            <div className="flex justify-end space-x-4">
                <Button
                    type="button"
                    variant="secondary"
                    onClick={handleDownloadTemplate}
                >
                    Download Template
                </Button>
                <Button
                    type="button"
                    variant="secondary"
                    onClick={() => window.history.back()}
                >
                    Cancel
                </Button>
                <Button
                    type="submit"
                    disabled={loading}
                >
                    {loading ? (
                        <div className="flex items-center">
                            <i className="fas fa-spinner fa-spin mr-2"></i>
                            Uploading...
                        </div>
                    ) : (
                        'Upload Listings'
                    )}
                </Button>
            </div>
        </form>
    );
}

BulkUploadForm.propTypes = {
    initialData: PropTypes.shape({
        csvFile: PropTypes.instanceOf(File),
        imageFiles: PropTypes.arrayOf(PropTypes.instanceOf(File)),
        location: PropTypes.string,
        notes: PropTypes.string,
        defaultType: PropTypes.oneOf(['donation', 'trade'])
    }),
    onSubmit: PropTypes.func.isRequired,
    loading: PropTypes.bool
};

export default BulkUploadForm;
