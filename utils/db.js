// Database store names
const STORES = {
    users: 'users',
    listings: 'listings',
};

// Initialize IndexedDB
function init() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open('dogoodsDB', 1);

        request.onerror = () => {
            reject(new Error('Failed to open database'));
        };

        request.onsuccess = (event) => {
            const db = event.target.result;
            resolve(db);
        };

        request.onupgradeneeded = (event) => {
            const db = event.target.result;

            // Create stores if they don't exist
            if (!db.objectStoreNames.contains(STORES.users)) {
                db.createObjectStore(STORES.users, { keyPath: 'id', autoIncrement: true });
            }
            if (!db.objectStoreNames.contains(STORES.listings)) {
                db.createObjectStore(STORES.listings, { keyPath: 'id', autoIncrement: true });
            }
        };
    });
}

// Add item to store
function add(storeName, item) {
    const db = init();
    return new Promise((resolve, reject) => {
        db.then(db => {
            const transaction = db.transaction(storeName, 'readwrite');
            const store = transaction.objectStore(storeName);
            const request = store.add(item);

            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(new Error('Failed to add item to store'));
        }).catch(reject);
    });
}

// Get item by id
function get(storeName, id) {
    const db = init();
    return new Promise((resolve, reject) => {
        db.then(db => {
            const transaction = db.transaction(storeName, 'readonly');
            const store = transaction.objectStore(storeName);
            const request = store.get(id);

            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(new Error('Failed to get item from store'));
        }).catch(reject);
    });
}

// Get all items from store
function getAll(storeName) {
    const db = init();
    return new Promise((resolve, reject) => {
        db.then(db => {
            const transaction = db.transaction(storeName, 'readonly');
            const store = transaction.objectStore(storeName);
            const request = store.getAll();

            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(new Error('Failed to get items from store'));
        }).catch(reject);
    });
}

// Update item
function update(storeName, id, updates) {
    const db = init();
    return new Promise((resolve, reject) => {
        db.then(db => {
            const transaction = db.transaction(storeName, 'readwrite');
            const store = transaction.objectStore(storeName);
            
            // First get the existing item
            const getRequest = store.get(id);
            
            getRequest.onsuccess = () => {
                const item = { ...getRequest.result, ...updates };
                const updateRequest = store.put(item);
                
                updateRequest.onsuccess = () => resolve(updateRequest.result);
                updateRequest.onerror = () => reject(new Error('Failed to update item'));
            };
            
            getRequest.onerror = () => reject(new Error('Failed to get item for update'));
        }).catch(reject);
    });
}

// Delete item
function deleteItem(storeName, id) {
    const db = init();
    return new Promise((resolve, reject) => {
        db.then(db => {
            const transaction = db.transaction(storeName, 'readwrite');
            const store = transaction.objectStore(storeName);
            const request = store.delete(id);

            request.onsuccess = () => resolve();
            request.onerror = () => reject(new Error('Failed to delete item'));
        }).catch(reject);
    });
}

export const db = {
    init,
    add,
    get,
    getAll,
    update,
    delete: deleteItem,
    STORES
};

export default db;
