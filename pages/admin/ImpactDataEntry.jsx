import React from 'react';
import AdminLayout from './AdminLayout';
import Button from '../../components/common/Button';
import supabase from '../../utils/supabaseClient';
import { useAuthContext } from '../../utils/AuthContext';

function ImpactDataEntry() {
    const { user } = useAuthContext();
    const [data, setData] = React.useState([]);
    const [loading, setLoading] = React.useState(true);
    const [editingId, setEditingId] = React.useState(null);
    const [newRow, setNewRow] = React.useState({
        date: new Date().toISOString().split('T')[0],
        food_saved_kg: 0,
        people_helped: 0,
        meals_provided: 0,
        co2_reduced_kg: 0,
        waste_diverted_kg: 0,
        volunteer_hours: 0,
        partner_organizations: 0,
        notes: ''
    });

    React.useEffect(() => {
        fetchData();

        const subscription = supabase
            .channel('impact-data')
            .on(
                'postgres_changes',
                {
                    event: '*',
                    schema: 'public',
                    table: 'impact_data'
                },
                () => {
                    console.log('Impact data changed, refreshing...');
                    fetchData();
                }
            )
            .subscribe();

        return () => {
            supabase.removeChannel(subscription);
        };
    }, []);

    const fetchData = async () => {
        try {
            setLoading(true);
            const { data: impactData, error } = await supabase
                .from('impact_data')
                .select('*')
                .order('date', { ascending: false });

            if (error) throw error;
            setData(impactData || []);
        } catch (error) {
            console.error('Error fetching impact data:', error);
            setData([]);
        } finally {
            setLoading(false);
        }
    };

    const handleAddRow = async () => {
        try {
            const { error } = await supabase
                .from('impact_data')
                .insert([{
                    ...newRow,
                    created_by: user?.id
                }]);

            if (error) throw error;

            setNewRow({
                date: new Date().toISOString().split('T')[0],
                food_saved_kg: 0,
                people_helped: 0,
                meals_provided: 0,
                co2_reduced_kg: 0,
                waste_diverted_kg: 0,
                volunteer_hours: 0,
                partner_organizations: 0,
                notes: ''
            });

            await fetchData();
        } catch (error) {
            console.error('Error adding row:', error);
            alert('Failed to add row: ' + error.message);
        }
    };

    const handleUpdateRow = async (id, field, value) => {
        try {
            const { error } = await supabase
                .from('impact_data')
                .update({
                    [field]: value,
                    updated_at: new Date().toISOString()
                })
                .eq('id', id);

            if (error) throw error;
            await fetchData();
        } catch (error) {
            console.error('Error updating row:', error);
            alert('Failed to update: ' + error.message);
        }
    };

    const handleDeleteRow = async (id) => {
        if (!confirm('Are you sure you want to delete this entry?')) return;

        try {
            const { error } = await supabase
                .from('impact_data')
                .delete()
                .eq('id', id);

            if (error) throw error;
            await fetchData();
        } catch (error) {
            console.error('Error deleting row:', error);
            alert('Failed to delete: ' + error.message);
        }
    };

    const handleCellChange = (id, field, value) => {
        if (id === 'new') {
            setNewRow(prev => ({ ...prev, [field]: value }));
        } else {
            setData(prev => prev.map(row =>
                row.id === id ? { ...row, [field]: value } : row
            ));
        }
    };

    const handleCellBlur = (id, field, value) => {
        if (id !== 'new') {
            handleUpdateRow(id, field, value);
        }
    };

    const exportToCSV = () => {
        const headers = ['Date', 'Food Saved (kg)', 'People Helped', 'Meals Provided',
                        'CO2 Reduced (kg)', 'Waste Diverted (kg)', 'Volunteer Hours',
                        'Partner Orgs', 'Notes'];

        const rows = data.map(row => [
            row.date,
            row.food_saved_kg,
            row.people_helped,
            row.meals_provided,
            row.co2_reduced_kg,
            row.waste_diverted_kg,
            row.volunteer_hours,
            row.partner_organizations,
            row.notes || ''
        ]);

        const csvContent = [headers, ...rows]
            .map(row => row.map(cell => `"${cell}"`).join(','))
            .join('\n');

        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);
        link.setAttribute('href', url);
        link.setAttribute('download', `impact_data_${new Date().toISOString()}.csv`);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

    const Cell = ({ value, onChange, onBlur, type = 'text', className = '' }) => (
        <input
            type={type}
            value={value}
            onChange={(e) => onChange(type === 'number' ? parseFloat(e.target.value) || 0 : e.target.value)}
            onBlur={(e) => onBlur(type === 'number' ? parseFloat(e.target.value) || 0 : e.target.value)}
            className={`w-full px-2 py-1 border border-gray-300 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent ${className}`}
        />
    );

    return (
        <AdminLayout active="impact">
            <div className="p-6">
                <div className="mb-6 flex justify-between items-center">
                    <div>
                        <h1 className="text-2xl font-bold text-gray-900">Impact Data Entry</h1>
                        <p className="mt-2 text-gray-600">Manually enter and manage impact metrics</p>
                    </div>
                    <div className="flex space-x-3">
                        <Button
                            variant="secondary"
                            onClick={fetchData}
                        >
                            <i className="fas fa-sync-alt mr-2"></i>
                            Refresh
                        </Button>
                        <Button
                            variant="primary"
                            onClick={exportToCSV}
                        >
                            <i className="fas fa-download mr-2"></i>
                            Export CSV
                        </Button>
                    </div>
                </div>

                {loading ? (
                    <div className="p-8 text-center">
                        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-green-600 mx-auto"></div>
                        <p className="mt-4 text-gray-600">Loading data...</p>
                    </div>
                ) : (
                    <div className="bg-white rounded-lg shadow overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200">
                            <thead className="bg-gray-50 sticky top-0">
                                <tr>
                                    <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-32">
                                        Date
                                    </th>
                                    <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-28">
                                        Food Saved (kg)
                                    </th>
                                    <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-28">
                                        People Helped
                                    </th>
                                    <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-28">
                                        Meals Provided
                                    </th>
                                    <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-28">
                                        CO2 Reduced (kg)
                                    </th>
                                    <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-28">
                                        Waste Diverted (kg)
                                    </th>
                                    <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-28">
                                        Volunteer Hours
                                    </th>
                                    <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-28">
                                        Partner Orgs
                                    </th>
                                    <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-48">
                                        Notes
                                    </th>
                                    <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-24">
                                        Actions
                                    </th>
                                </tr>
                            </thead>
                            <tbody className="bg-white divide-y divide-gray-200">
                                <tr className="bg-green-50">
                                    <td className="px-3 py-2">
                                        <Cell
                                            type="date"
                                            value={newRow.date}
                                            onChange={(val) => handleCellChange('new', 'date', val)}
                                            onBlur={() => {}}
                                        />
                                    </td>
                                    <td className="px-3 py-2">
                                        <Cell
                                            type="number"
                                            value={newRow.food_saved_kg}
                                            onChange={(val) => handleCellChange('new', 'food_saved_kg', val)}
                                            onBlur={() => {}}
                                        />
                                    </td>
                                    <td className="px-3 py-2">
                                        <Cell
                                            type="number"
                                            value={newRow.people_helped}
                                            onChange={(val) => handleCellChange('new', 'people_helped', val)}
                                            onBlur={() => {}}
                                        />
                                    </td>
                                    <td className="px-3 py-2">
                                        <Cell
                                            type="number"
                                            value={newRow.meals_provided}
                                            onChange={(val) => handleCellChange('new', 'meals_provided', val)}
                                            onBlur={() => {}}
                                        />
                                    </td>
                                    <td className="px-3 py-2">
                                        <Cell
                                            type="number"
                                            value={newRow.co2_reduced_kg}
                                            onChange={(val) => handleCellChange('new', 'co2_reduced_kg', val)}
                                            onBlur={() => {}}
                                        />
                                    </td>
                                    <td className="px-3 py-2">
                                        <Cell
                                            type="number"
                                            value={newRow.waste_diverted_kg}
                                            onChange={(val) => handleCellChange('new', 'waste_diverted_kg', val)}
                                            onBlur={() => {}}
                                        />
                                    </td>
                                    <td className="px-3 py-2">
                                        <Cell
                                            type="number"
                                            value={newRow.volunteer_hours}
                                            onChange={(val) => handleCellChange('new', 'volunteer_hours', val)}
                                            onBlur={() => {}}
                                        />
                                    </td>
                                    <td className="px-3 py-2">
                                        <Cell
                                            type="number"
                                            value={newRow.partner_organizations}
                                            onChange={(val) => handleCellChange('new', 'partner_organizations', val)}
                                            onBlur={() => {}}
                                        />
                                    </td>
                                    <td className="px-3 py-2">
                                        <Cell
                                            value={newRow.notes}
                                            onChange={(val) => handleCellChange('new', 'notes', val)}
                                            onBlur={() => {}}
                                        />
                                    </td>
                                    <td className="px-3 py-2">
                                        <Button
                                            variant="primary"
                                            size="sm"
                                            onClick={handleAddRow}
                                        >
                                            <i className="fas fa-plus"></i>
                                        </Button>
                                    </td>
                                </tr>

                                {data.map((row) => (
                                    <tr key={row.id} className="hover:bg-gray-50">
                                        <td className="px-3 py-2">
                                            <Cell
                                                type="date"
                                                value={row.date}
                                                onChange={(val) => handleCellChange(row.id, 'date', val)}
                                                onBlur={(val) => handleCellBlur(row.id, 'date', val)}
                                            />
                                        </td>
                                        <td className="px-3 py-2">
                                            <Cell
                                                type="number"
                                                value={row.food_saved_kg}
                                                onChange={(val) => handleCellChange(row.id, 'food_saved_kg', val)}
                                                onBlur={(val) => handleCellBlur(row.id, 'food_saved_kg', val)}
                                            />
                                        </td>
                                        <td className="px-3 py-2">
                                            <Cell
                                                type="number"
                                                value={row.people_helped}
                                                onChange={(val) => handleCellChange(row.id, 'people_helped', val)}
                                                onBlur={(val) => handleCellBlur(row.id, 'people_helped', val)}
                                            />
                                        </td>
                                        <td className="px-3 py-2">
                                            <Cell
                                                type="number"
                                                value={row.meals_provided}
                                                onChange={(val) => handleCellChange(row.id, 'meals_provided', val)}
                                                onBlur={(val) => handleCellBlur(row.id, 'meals_provided', val)}
                                            />
                                        </td>
                                        <td className="px-3 py-2">
                                            <Cell
                                                type="number"
                                                value={row.co2_reduced_kg}
                                                onChange={(val) => handleCellChange(row.id, 'co2_reduced_kg', val)}
                                                onBlur={(val) => handleCellBlur(row.id, 'co2_reduced_kg', val)}
                                            />
                                        </td>
                                        <td className="px-3 py-2">
                                            <Cell
                                                type="number"
                                                value={row.waste_diverted_kg}
                                                onChange={(val) => handleCellChange(row.id, 'waste_diverted_kg', val)}
                                                onBlur={(val) => handleCellBlur(row.id, 'waste_diverted_kg', val)}
                                            />
                                        </td>
                                        <td className="px-3 py-2">
                                            <Cell
                                                type="number"
                                                value={row.volunteer_hours}
                                                onChange={(val) => handleCellChange(row.id, 'volunteer_hours', val)}
                                                onBlur={(val) => handleCellBlur(row.id, 'volunteer_hours', val)}
                                            />
                                        </td>
                                        <td className="px-3 py-2">
                                            <Cell
                                                type="number"
                                                value={row.partner_organizations}
                                                onChange={(val) => handleCellChange(row.id, 'partner_organizations', val)}
                                                onBlur={(val) => handleCellBlur(row.id, 'partner_organizations', val)}
                                            />
                                        </td>
                                        <td className="px-3 py-2">
                                            <Cell
                                                value={row.notes || ''}
                                                onChange={(val) => handleCellChange(row.id, 'notes', val)}
                                                onBlur={(val) => handleCellBlur(row.id, 'notes', val)}
                                            />
                                        </td>
                                        <td className="px-3 py-2">
                                            <Button
                                                variant="danger"
                                                size="sm"
                                                onClick={() => handleDeleteRow(row.id)}
                                            >
                                                <i className="fas fa-trash"></i>
                                            </Button>
                                        </td>
                                    </tr>
                                ))}

                                {data.length === 0 && (
                                    <tr>
                                        <td colSpan="10" className="px-6 py-8 text-center text-gray-500">
                                            No data entries yet. Add your first entry using the row above.
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                )}

                <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-4">
                    <h3 className="text-sm font-semibold text-blue-900 mb-2">
                        <i className="fas fa-info-circle mr-2"></i>
                        How to use this spreadsheet
                    </h3>
                    <ul className="text-sm text-blue-800 space-y-1">
                        <li>• Fill in the green row at the top to add a new entry</li>
                        <li>• Click the + button to save the new entry</li>
                        <li>• Click on any cell to edit existing data</li>
                        <li>• Changes are saved automatically when you click outside the cell</li>
                        <li>• Use the trash icon to delete an entry</li>
                        <li>• Export to CSV for backup or further analysis</li>
                    </ul>
                </div>
            </div>
        </AdminLayout>
    );
}

export default ImpactDataEntry;
