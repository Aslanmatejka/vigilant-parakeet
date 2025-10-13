import React from "react";
import Card from "../components/common/Card";
import ErrorBoundary from "../components/common/ErrorBoundary";
import { reportError } from "../utils/helpers";
import { useAuth, useNotifications } from "../utils/hooks/useSupabase";

function Notifications() {
    const { user: authUser, isAuthenticated } = useAuth();
    const { notifications, loading, error, markAsRead, unreadCount } = useNotifications(authUser?.id);

    React.useEffect(() => {
        if (!isAuthenticated) {
            window.location.href = '/login';
            return;
        }
    }, [isAuthenticated]);

    const handleMarkAsRead = async (notificationId) => {
        try {
            await markAsRead(notificationId);
        } catch (error) {
            console.error('Error marking notification as read:', error);
            reportError(error);
        }
    };

    if (!isAuthenticated) {
        return null; // Will redirect in useEffect
    }

    if (loading) {
        return (
            <div className="max-w-4xl mx-auto py-8 px-4">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto"></div>
                    <p className="mt-4 text-gray-600">Loading notifications...</p>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="max-w-4xl mx-auto py-8 px-4">
                <div className="text-center">
                    <p className="text-red-600">Error loading notifications: {error}</p>
                </div>
            </div>
        );
    }

    const deleteNotification = async (notificationId) => {
        try {
            // TODO: Implement delete notification functionality in useNotifications hook
            console.log('Delete notification functionality not implemented yet');
        } catch (error) {
            console.error('Error deleting notification:', error);
            reportError(error);
        }
    };

    const getNotificationIcon = (type) => {
        switch (type) {
            case 'food_claimed':
                return 'fa-hand-holding-heart';
            case 'trade_request':
                return 'fa-exchange-alt';
            case 'system':
                return 'fa-bell';
            default:
                return 'fa-info-circle';
        }
    };

    const getNotificationTypeLabel = (type) => {
        switch (type) {
            case 'food_claimed':
                return 'Food Claimed Notification';
            case 'trade_request':
                return 'Trade Request Notification';
            case 'system':
                return 'System Notification';
            default:
                return 'Notification';
        }
    };

    return (
        <ErrorBoundary>
            <main 
                className="max-w-4xl mx-auto py-8 px-4"
                role="main"
                aria-labelledby="notifications-title"
            >
                <div className="flex justify-between items-center mb-8">
                    <h1 
                        id="notifications-title" 
                        className="text-3xl font-bold text-gray-900"
                    >
                        Notifications
                    </h1>
                    <div className="space-x-4">
                        <Button
                            variant="secondary"
                            onClick={markAllAsRead}
                            disabled={notifications.every(n => n.read)}
                            aria-label="Mark all notifications as read"
                        >
                            Mark All as Read
                        </Button>
                    </div>
                </div>

                <div 
                    className="space-y-4"
                    role="feed"
                    aria-label="Notifications list"
                >
                    {notifications.length === 0 ? (
                        <div 
                            className="text-center py-12"
                            role="status"
                            aria-label="No notifications"
                        >
                            <i 
                                className="fas fa-bell text-gray-400 text-4xl mb-4"
                                aria-hidden="true"
                            ></i>
                            <p className="text-gray-600">No notifications yet</p>
                        </div>
                    ) : (
                        notifications.map(notification => (
                            <Card
                                key={notification.id}
                                className={`transition-colors duration-200 ${
                                    notification.read ? 'bg-white' : 'bg-green-50'
                                }`}
                                role="article"
                                aria-labelledby={`notification-${notification.id}-title`}
                            >
                                <div className="p-4">
                                    <div className="flex items-start">
                                        <div className="flex-shrink-0">
                                            <div 
                                                className="w-10 h-10 bg-green-100 rounded-full flex items-center justify-center"
                                                aria-hidden="true"
                                            >
                                                <i className={`fas ${getNotificationIcon(notification.type)} text-green-600`}></i>
                                            </div>
                                        </div>
                                        <div className="ml-4 flex-1">
                                            <div className="flex items-center justify-between">
                                                <h2 
                                                    id={`notification-${notification.id}-title`}
                                                    className="text-lg font-semibold text-gray-900"
                                                >
                                                    {notification.title}
                                                </h2>
                                                <div className="flex items-center space-x-4">
                                                    <time 
                                                        className="text-sm text-gray-500"
                                                        dateTime={notification.time}
                                                    >
                                                        {notification.time}
                                                    </time>
                                                    <div className="flex space-x-2">
                                                        {!notification.read && (
                                                            <Button
                                                                variant="icon"
                                                                onClick={() => handleMarkAsRead(notification.id)}
                                                                aria-label={`Mark "${notification.title}" as read`}
                                                                icon={<i className="fas fa-check" aria-hidden="true"></i>}
                                                            />
                                                        )}
                                                        <Button
                                                            variant="icon"
                                                            onClick={() => deleteNotification(notification.id)}
                                                            aria-label={`Delete "${notification.title}" notification`}
                                                            icon={<i className="fas fa-trash" aria-hidden="true"></i>}
                                                        />
                                                    </div>
                                                </div>
                                            </div>
                                            <p 
                                                className="mt-1 text-gray-600"
                                                aria-label={getNotificationTypeLabel(notification.type)}
                                            >
                                                {notification.message}
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            </Card>
                        ))
                    )}
                </div>
            </main>
        </ErrorBoundary>
    );
}

export default Notifications;
