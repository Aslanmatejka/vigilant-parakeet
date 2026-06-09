import { useState, useEffect } from 'react';
import { toast } from 'react-toastify';
import dataService from '../../utils/dataService';
import Button from '../common/Button';
import Input from '../common/Input';

const DonationScheduleForm = ({ schedule = null, onSuccess, onCancel }) => {
  const [formData, setFormData] = useState({
    title: '',
    amount: '',
    frequency: 'monthly',
    start_date: (() => { const _d = new Date(); return [_d.getFullYear(), String(_d.getMonth()+1).padStart(2,'0'), String(_d.getDate()).padStart(2,'0')].join('-'); })(),
    end_date: '',
    recipient_type: 'general',
    recipient_id: '',
    payment_method: 'card',
    notes: '',
    reminder_enabled: true,
    reminder_days_before: 1
  });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (schedule) {
      setFormData({
        title: schedule.title || '',
        amount: schedule.amount || '',
        frequency: schedule.frequency || 'monthly',
        start_date: schedule.start_date || (() => { const _d = new Date(); return [_d.getFullYear(), String(_d.getMonth()+1).padStart(2,'0'), String(_d.getDate()).padStart(2,'0')].join('-'); })(),
        end_date: schedule.end_date || '',
        recipient_type: schedule.recipient_type || 'general',
        recipient_id: schedule.recipient_id || '',
        payment_method: schedule.payment_method || 'card',
        notes: schedule.notes || '',
        reminder_enabled: schedule.reminder_enabled !== false,
        reminder_days_before: schedule.reminder_days_before || 1
      });
    }
  }, [schedule]);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      const amount = parseFloat(formData.amount);
      if (isNaN(amount) || amount <= 0) {
        toast.error('Please enter a valid amount');
        return;
      }

      const startDate = new Date(formData.start_date);
      if (isNaN(startDate.getTime())) {
        toast.error('Please enter a valid start date');
        return;
      }

      if (formData.end_date) {
        const endDate = new Date(formData.end_date);
        if (endDate <= startDate) {
          toast.error('End date must be after start date');
          return;
        }
      }

      const nextDonationDate = dataService.calculateNextDonationDate(
        formData.start_date,
        formData.frequency
      );

      const scheduleData = {
        ...formData,
        amount,
        next_donation_date: nextDonationDate,
        status: 'active'
      };

      if (!formData.end_date) {
        delete scheduleData.end_date;
      }
      if (!formData.recipient_id) {
        delete scheduleData.recipient_id;
      }

      let result;
      if (schedule) {
        result = await dataService.updateDonationSchedule(schedule.id, scheduleData);
        toast.success('Donation schedule updated successfully!');
      } else {
        result = await dataService.createDonationSchedule(scheduleData);
        toast.success('Donation schedule created successfully!');
      }

      if (onSuccess) {
        onSuccess(result);
      }
    } catch (error) {
      console.error('Error saving donation schedule:', error);
      toast.error(error.message || 'Failed to save donation schedule');
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6 bg-white p-6 rounded-lg shadow-md">
      <h3 className="text-2xl font-bold text-gray-800 mb-4">
        {schedule ? 'Edit Donation Schedule' : 'Create Donation Schedule'}
      </h3>

      <div className="space-y-4">
        <div>
          <label htmlFor="title" className="block text-sm font-medium text-gray-700 mb-1">
            Schedule Name *
          </label>
          <Input
            id="title"
            name="title"
            type="text"
            value={formData.title}
            onChange={handleChange}
            placeholder="e.g., Monthly Food Bank Donation"
            required
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label htmlFor="amount" className="block text-sm font-medium text-gray-700 mb-1">
              Amount ($) *
            </label>
            <Input
              id="amount"
              name="amount"
              type="number"
              step="0.01"
              min="0.01"
              value={formData.amount}
              onChange={handleChange}
              placeholder="25.00"
              required
            />
          </div>

          <div>
            <label htmlFor="frequency" className="block text-sm font-medium text-gray-700 mb-1">
              Frequency *
            </label>
            <select
              id="frequency"
              name="frequency"
              value={formData.frequency}
              onChange={handleChange}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
              required
            >
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
              <option value="yearly">Yearly</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label htmlFor="start_date" className="block text-sm font-medium text-gray-700 mb-1">
              Start Date *
            </label>
            <Input
              id="start_date"
              name="start_date"
              type="date"
              value={formData.start_date}
              onChange={handleChange}
              required
            />
          </div>

          <div>
            <label htmlFor="end_date" className="block text-sm font-medium text-gray-700 mb-1">
              End Date (Optional)
            </label>
            <Input
              id="end_date"
              name="end_date"
              type="date"
              value={formData.end_date}
              onChange={handleChange}
            />
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label htmlFor="recipient_type" className="block text-sm font-medium text-gray-700 mb-1">
              Donation To *
            </label>
            <select
              id="recipient_type"
              name="recipient_type"
              value={formData.recipient_type}
              onChange={handleChange}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
              required
            >
              <option value="general">General Fund</option>
              <option value="organization">Organization</option>
              <option value="food_bank">Food Bank</option>
              <option value="community">Community</option>
              <option value="specific_listing">Specific Listing</option>
            </select>
          </div>

          <div>
            <label htmlFor="payment_method" className="block text-sm font-medium text-gray-700 mb-1">
              Payment Method *
            </label>
            <select
              id="payment_method"
              name="payment_method"
              value={formData.payment_method}
              onChange={handleChange}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
              required
            >
              <option value="card">Credit/Debit Card</option>
              <option value="bank_transfer">Bank Transfer</option>
              <option value="paypal">PayPal</option>
              <option value="other">Other</option>
            </select>
          </div>
        </div>

        <div className="border-t pt-4">
          <div className="flex items-center mb-3">
            <input
              id="reminder_enabled"
              name="reminder_enabled"
              type="checkbox"
              checked={formData.reminder_enabled}
              onChange={handleChange}
              className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
            />
            <label htmlFor="reminder_enabled" className="ml-2 block text-sm text-gray-700">
              Enable donation reminders
            </label>
          </div>

          {formData.reminder_enabled && (
            <div>
              <label htmlFor="reminder_days_before" className="block text-sm font-medium text-gray-700 mb-1">
                Remind me (days before)
              </label>
              <Input
                id="reminder_days_before"
                name="reminder_days_before"
                type="number"
                min="0"
                max="30"
                value={formData.reminder_days_before}
                onChange={handleChange}
              />
            </div>
          )}
        </div>

        <div>
          <label htmlFor="notes" className="block text-sm font-medium text-gray-700 mb-1">
            Notes (Optional)
          </label>
          <textarea
            id="notes"
            name="notes"
            value={formData.notes}
            onChange={handleChange}
            rows={3}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            placeholder="Add any additional notes about this donation schedule..."
          />
        </div>
      </div>

      <div className="flex gap-3 pt-4">
        <Button
          type="submit"
          disabled={loading}
          className="flex-1"
        >
          {loading ? 'Saving...' : schedule ? 'Update Schedule' : 'Create Schedule'}
        </Button>
        {onCancel && (
          <Button
            type="button"
            onClick={onCancel}
            variant="secondary"
            disabled={loading}
          >
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
};

export default DonationScheduleForm;
