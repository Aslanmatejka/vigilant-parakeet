import React from 'react';
import { useNavigate } from 'react-router-dom';
import AdminLayout from './AdminLayout';
import Button from '../../components/common/Button';
import Card from '../../components/common/Card';
import Input from '../../components/common/Input';
import { reportError } from '../../utils/helpers';
import { toast } from 'react-toastify';

const formatDate = (dateString) => {
    if (!dateString) return '';
    return new Date(dateString).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    });
};

function FoodDistributionManagement() {
    try {
        const navigate = useNavigate();
        const [distributions, setDistributions] = React.useState([]);
        const [loading, setLoading] = React.useState(true);
        const [submitting, setSubmitting] = React.useState(false);
        const [error, setError] = React.useState(null);
        const [showForm, setShowForm] = React.useState(false);
        const [formData, setFormData] = React.useState({
            title: '',
            location: '',
            date: '',
            time: '',
            capacity: '',
            description: '',
            status: 'scheduled'
        });

        React.useEffect(() => {
            loadDistributions();
        }, []);

        const validateForm = () => {
            const errors = [];
            
            if (!formData.title.trim()) {
                errors.push('Event title is required');
            }
            if (!formData.location.trim()) {
                errors.push('Location is required');
            }
            if (!formData.date) {
                errors.push('Date is required');
            } else if (new Date(formData.date) < new Date().setHours(0, 0, 0, 0)) {
                errors.push('Date cannot be in the past');
            }
            if (!formData.time.trim()) {
                errors.push('Time is required');
            }
            if (!formData.capacity || formData.capacity < 1) {
                errors.push('Capacity must be at least 1');
            }
            if (!formData.description.trim()) {
                errors.push('Description is required');
            }
            
            return errors;
        };

        const handleSubmit = async (e) => {
            e.preventDefault();
            const errors = validateForm();
            if (errors.length > 0) {
                errors.forEach(error => toast.error(error));
                return;
            }

            setSubmitting(true);
            try {
                // Simulated API call
                await new Promise(resolve => setTimeout(resolve, 1000));
                
                const newDistribution = {
                    id: distributions.length + 1,
                    ...formData,
                    registered: 0
                };
                
                setDistributions([...distributions, newDistribution]);
                setShowForm(false);
                setFormData({
                    title: '',
                    location: '',
                    date: '',
                    time: '',
                    capacity: '',
                    description: '',
                    status: 'scheduled'
                });
                toast.success('Distribution event created successfully');
            } catch (error) {
                console.error('Create distribution error:', error);
                toast.error('Failed to create distribution event');
            } finally {
                setSubmitting(false);
            }
        };

        const handleDelete = async (id) => {
            const confirmed = window.confirm('Are you sure you want to delete this distribution event? This action cannot be undone.');
            if (!confirmed) return;
            
            try {
                setLoading(true);
                // Simulated API call
                await new Promise(resolve => setTimeout(resolve, 500));
                setDistributions(distributions.filter(dist => dist.id !== id));
                toast.success('Distribution event deleted successfully');
            } catch (error) {
                console.error('Delete distribution error:', error);
                toast.error('Failed to delete distribution event');
            } finally {
                setLoading(false);
            }
        };

        const handleStatusChange = async (id, status) => {
            try {
                setLoading(true);
                // Simulated API call
                await new Promise(resolve => setTimeout(resolve, 500));
                setDistributions(distributions.map(dist => 
                    dist.id === id ? { ...dist, status } : dist
                ));
                toast.success(`Event status updated to ${status}`);
            } catch (error) {
                console.error('Update status error:', error);
                toast.error('Failed to update status');
            } finally {
                setLoading(false);
            }
        };

        const getStatusBadge = (status) => {
            const statusStyles = {
                scheduled: 'bg-blue-100 text-blue-800',
                full: 'bg-yellow-100 text-yellow-800',
                completed: 'bg-green-100 text-green-800',
                cancelled: 'bg-red-100 text-red-800'
            };
            
            return (
                <span className={`px-2 py-1 text-xs rounded-full ${statusStyles[status]}`}>
                    {status.charAt(0).toUpperCase() + status.slice(1)}
                </span>
            );
        };

        return (
            <AdminLayout active="distribution">
                <div data-name="food-distribution-management" className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
                    <div className="flex justify-between items-center mb-8">
                        <div>
                            <h1 className="text-3xl font-bold text-gray-900">Food Distribution Management</h1>
                            <p className="mt-2 text-gray-600">
                                Manage food distribution events and track attendance.
                            </p>
                        </div>
                        <Button
                            variant="primary"
                            icon={<i className="fas fa-plus"></i>}
                            onClick={() => setShowForm(!showForm)}
                        >
                            {showForm ? 'Cancel' : 'Create Event'}
                        </Button>
                    </div>

                    {showForm && (
                        <Card className="mb-8">
                            <form onSubmit={handleSubmit} className="p-6">
                                <h2 className="text-xl font-semibold mb-6">Create Distribution Event</h2>
                                
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
                                    <Input
                                        label="Event Title"
                                        name="title"
                                        value={formData.title}
                                        onChange={handleInputChange}
                                        required
                                    />
                                    
                                    <Input
                                        label="Location"
                                        name="location"
                                        value={formData.location}
                                        onChange={handleInputChange}
                                        required
                                    />
                                    
                                    <Input
                                        label="Date"
                                        name="date"
                                        type="date"
                                        value={formData.date}
                                        onChange={handleInputChange}
                                        required
                                    />
                                    
                                    <Input
                                        label="Time"
                                        name="time"
                                        value={formData.time}
                                        onChange={handleInputChange}
                                        placeholder="e.g. 10:00 AM - 2:00 PM"
                                        required
                                    />
                                    
                                    <Input
                                        label="Capacity"
                                        name="capacity"
                                        type="number"
                                        value={formData.capacity}
                                        onChange={handleInputChange}
                                        required
                                    />
                                    
                                    <Input
                                        label="Status"
                                        name="status"
                                        type="select"
                                        value={formData.status}
                                        onChange={handleInputChange}
                                        options={[
                                            { value: 'scheduled', label: 'Scheduled' },
                                            { value: 'full', label: 'Full' },
                                            { value: 'completed', label: 'Completed' },
                                            { value: 'cancelled', label: 'Cancelled' }
                                        ]}
                                        required
                                    />
                                    
                                    <div className="md:col-span-2">
                                        <Input
                                            label="Description"
                                            name="description"
                                            type="textarea"
                                            value={formData.description}
                                            onChange={handleInputChange}
                                            required
                                        />
                                    </div>
                                </div>
                                
                                <div className="flex justify-end space-x-4">
                                    <Button
                                        variant="secondary"
                                        type="button"
                                        onClick={() => setShowForm(false)}
                                    >
                                        Cancel
                                    </Button>
                                    <Button
                                        variant="primary"
                                        type="submit"
                                        disabled={submitting}
                                    >
                                        {submitting ? 'Creating...' : 'Create Event'}
                                    </Button>
                                </div>
                            </form>
                        </Card>
                    )}

                    {loading ? (
                        <div className="space-y-4">
                            {[1, 2, 3].map(i => (
                                <div key={i} className="animate-pulse bg-gray-200 rounded-lg h-32"></div>
                            ))}
                        </div>
                    ) : error ? (
                        <div className="text-center py-8">
                            <i className="fas fa-exclamation-circle text-red-500 text-4xl mb-4"></i>
                            <p className="text-gray-600">{error}</p>
                            <Button
                                variant="secondary"
                                className="mt-4"
                                onClick={loadDistributions}
                            >
                                Try Again
                            </Button>
                        </div>
                    ) : (
                        <div className="overflow-x-auto">
                            <table 
                                className="min-w-full divide-y divide-gray-200"
                                role="table"
                                aria-label="Distribution Events"
                            >
                                <thead>
                                    <tr>
                                        <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                            Event
                                        </th>
                                        <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                            Date & Time
                                        </th>
                                        <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                            Location
                                        </th>
                                        <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                            Capacity
                                        </th>
                                        <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                            Status
                                        </th>
                                        <th scope="col" className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                                            Actions
                                        </th>
                                    </tr>
                                </thead>
                                <tbody className="bg-white divide-y divide-gray-200">
                                    {distributions.map(dist => (
                                        <tr key={dist.id}>
                                            <td className="px-6 py-4 whitespace-nowrap">
                                                <div className="font-medium text-gray-900">{dist.title}</div>
                                                <div className="text-sm text-gray-500 truncate max-w-xs">
                                                    {dist.description}
                                                </div>
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap">
                                                <div className="text-sm text-gray-900">{formatDate(dist.date)}</div>
                                                <div className="text-sm text-gray-500">{dist.time}</div>
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                                {dist.location}
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap">
                                                <div className="text-sm text-gray-900">
                                                    {dist.registered} / {dist.capacity}
                                                </div>
                                                <div 
                                                    className="w-full bg-gray-200 rounded-full h-2 mt-1"
                                                    role="progressbar"
                                                    aria-valuenow={dist.registered}
                                                    aria-valuemin="0"
                                                    aria-valuemax={dist.capacity}
                                                    aria-label={`${dist.registered} out of ${dist.capacity} spots filled`}
                                                >
                                                    <div 
                                                        className="bg-green-600 h-2 rounded-full" 
                                                        style={{ width: `${(dist.registered / dist.capacity) * 100}%` }}
                                                    ></div>
                                                </div>
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap">
                                                {getStatusBadge(dist.status)}
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                                <div className="flex justify-end space-x-2">
                                                    <Button
                                                        variant="secondary"
                                                        size="sm"
                                                        icon={<i className="fas fa-users" aria-hidden="true"></i>}
                                                        onClick={() => navigate(`/admin/distribution/${dist.id}/attendees`)}
                                                        aria-label={`View attendees for ${dist.title}`}
                                                    >
                                                        Attendees
                                                    </Button>
                                                    
                                                    <Button
                                                        variant="secondary"
                                                        size="sm"
                                                        icon={<i className="fas fa-edit" aria-hidden="true"></i>}
                                                        onClick={() => navigate(`/admin/distribution/${dist.id}/edit`)}
                                                        aria-label={`Edit ${dist.title}`}
                                                    >
                                                        Edit
                                                    </Button>
                                                    
                                                    {dist.status !== 'completed' && dist.status !== 'cancelled' && (
                                                        <Button
                                                            variant="primary"
                                                            size="sm"
                                                            icon={<i className="fas fa-check-circle" aria-hidden="true"></i>}
                                                            onClick={() => handleStatusChange(dist.id, 'completed')}
                                                            aria-label={`Mark ${dist.title} as completed`}
                                                        >
                                                            Complete
                                                        </Button>
                                                    )}
                                                    
                                                    {dist.status !== 'cancelled' && (
                                                        <Button
                                                            variant="danger"
                                                            size="sm"
                                                            icon={<i className="fas fa-ban" aria-hidden="true"></i>}
                                                            onClick={() => handleStatusChange(dist.id, 'cancelled')}
                                                            aria-label={`Cancel ${dist.title}`}
                                                        >
                                                            Cancel
                                                        </Button>
                                                    )}
                                                    
                                                    <Button
                                                        variant="danger"
                                                        size="sm"
                                                        icon={<i className="fas fa-trash" aria-hidden="true"></i>}
                                                        onClick={() => handleDelete(dist.id)}
                                                        aria-label={`Delete ${dist.title}`}
                                                    >
                                                        Delete
                                                    </Button>
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            </AdminLayout>
        );
    } catch (error) {
        console.error('FoodDistributionManagement error:', error);
        reportError(error);
        return null;
    }
}

export default FoodDistributionManagement;
