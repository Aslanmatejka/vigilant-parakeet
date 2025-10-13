// Update the mock attendee data with proper profile images:

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
