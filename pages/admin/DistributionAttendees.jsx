import React from 'react';

const DistributionAttendees = () => {
  const mockAttendees = [
    {
      id: 1,
      name: 'John Smith',
      email: 'john@example.com',
      phone: '555-0123',
      familySize: 3,
      checkIn: new Date().toISOString(),
      foodReceived: true,
      avatar: 'https://randomuser.me/api/portraits/men/2.jpg'
    },
    {
      id: 2,
      name: 'Maria Rodriguez',
      email: 'maria@example.com',
      phone: '555-0124',
      familySize: 4,
      checkIn: new Date().toISOString(),
      foodReceived: true,
      avatar: 'https://randomuser.me/api/portraits/women/3.jpg'
    },
    {
      id: 3,
      name: 'David Lee',
      email: 'david@example.com',
      phone: '555-0125',
      familySize: 2,
      checkIn: new Date().toISOString(),
      foodReceived: false,
      avatar: 'https://randomuser.me/api/portraits/men/3.jpg'
    }
  ];

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6">Distribution Attendees</h1>
      
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold">Event Attendees</h2>
        </div>
        
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Attendee
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Contact
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Family Size
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Check-in Time
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Food Received
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {mockAttendees.map(attendee => (
                <tr key={attendee.id}>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center">
                      <img 
                        className="h-10 w-10 rounded-full" 
                        src={attendee.avatar} 
                        alt={attendee.name} 
                      />
                      <div className="ml-4">
                        <div className="text-sm font-medium text-gray-900">{attendee.name}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm text-gray-900">{attendee.email}</div>
                    <div className="text-sm text-gray-500">{attendee.phone}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    {attendee.familySize} people
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {new Date(attendee.checkIn).toLocaleTimeString()}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                      attendee.foodReceived ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                    }`}>
                      {attendee.foodReceived ? 'Yes' : 'No'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default DistributionAttendees; 