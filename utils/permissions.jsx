// User Types
const USER_TYPES = {
    ADMIN: 'admin',
    DONOR: 'donor',
    RECIPIENT: 'recipient',
    VOLUNTEER: 'volunteer',
    USER: 'user'
};

// Permission Levels
const PERMISSIONS = {
    CREATE_LISTING: 'create_listing',
    EDIT_LISTING: 'edit_listing',
    DELETE_LISTING: 'delete_listing',
    MANAGE_USERS: 'manage_users',
    MANAGE_CONTENT: 'manage_content',
    MANAGE_DISTRIBUTIONS: 'manage_distributions',
    VIEW_ANALYTICS: 'view_analytics',
    TRADE: 'trade',
    CLAIM: 'claim',
    VOLUNTEER: 'volunteer'
};

// Permission mappings for each user type
const USER_PERMISSIONS = {
    [USER_TYPES.ADMIN]: [
        PERMISSIONS.CREATE_LISTING,
        PERMISSIONS.EDIT_LISTING,
        PERMISSIONS.DELETE_LISTING,
        PERMISSIONS.MANAGE_USERS,
        PERMISSIONS.MANAGE_CONTENT,
        PERMISSIONS.MANAGE_DISTRIBUTIONS,
        PERMISSIONS.VIEW_ANALYTICS,
        PERMISSIONS.TRADE,
        PERMISSIONS.CLAIM,
        PERMISSIONS.VOLUNTEER
    ],
    [USER_TYPES.DONOR]: [
        PERMISSIONS.CREATE_LISTING,
        PERMISSIONS.EDIT_LISTING,
        PERMISSIONS.DELETE_LISTING,
        PERMISSIONS.TRADE,
        PERMISSIONS.VOLUNTEER
    ],
    [USER_TYPES.RECIPIENT]: [
        PERMISSIONS.CLAIM,
        PERMISSIONS.TRADE
    ],
    [USER_TYPES.VOLUNTEER]: [
        PERMISSIONS.VOLUNTEER,
        PERMISSIONS.CLAIM,
        PERMISSIONS.TRADE
    ],
    [USER_TYPES.USER]: [
        PERMISSIONS.CLAIM,
        PERMISSIONS.TRADE
    ]
};

// Check if user has specific permission
function hasPermission(userType, permission) {
    if (!userType || !permission) return false;
    return USER_PERMISSIONS[userType]?.includes(permission) || false;
}

// Get all permissions for a user type
function getUserPermissions(userType) {
    return USER_PERMISSIONS[userType] || [];
}

// Check if user can perform specific actions
const can = {
    createListing: (userType) => hasPermission(userType, PERMISSIONS.CREATE_LISTING),
    editListing: (userType) => hasPermission(userType, PERMISSIONS.EDIT_LISTING),
    deleteListing: (userType) => hasPermission(userType, PERMISSIONS.DELETE_LISTING),
    manageUsers: (userType) => hasPermission(userType, PERMISSIONS.MANAGE_USERS),
    manageContent: (userType) => hasPermission(userType, PERMISSIONS.MANAGE_CONTENT),
    manageDistributions: (userType) => hasPermission(userType, PERMISSIONS.MANAGE_DISTRIBUTIONS),
    viewAnalytics: (userType) => hasPermission(userType, PERMISSIONS.VIEW_ANALYTICS),
    trade: (userType) => hasPermission(userType, PERMISSIONS.TRADE),
    claim: (userType) => hasPermission(userType, PERMISSIONS.CLAIM),
    volunteer: (userType) => hasPermission(userType, PERMISSIONS.VOLUNTEER)
};

// Export the permissions
export { can, hasPermission, getUserPermissions, USER_TYPES, PERMISSIONS, USER_PERMISSIONS };
