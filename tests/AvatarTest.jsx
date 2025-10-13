// Simple test to verify Avatar component fallback behavior
import React from 'react';
import Avatar from '../components/common/Avatar.jsx';

// Test component to verify Avatar fallback behavior
function AvatarTest() {
    return (
        <div style={{ padding: '20px', display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
            <div>
                <h3>Valid Image</h3>
                <Avatar src="https://ui-avatars.com/api/?name=John+Doe&background=6366f1" alt="John Doe" />
            </div>
            
            <div>
                <h3>Invalid Image (should fallback)</h3>
                <Avatar src="https://invalid-url.com/broken.jpg" alt="Jane Smith" />
            </div>
            
            <div>
                <h3>No Image (should fallback)</h3>
                <Avatar alt="Bob Johnson" />
            </div>
            
            <div>
                <h3>Null Image (should fallback)</h3>
                <Avatar src={null} alt="Alice Brown" />
            </div>
        </div>
    );
}

export default AvatarTest;
