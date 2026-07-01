import React from "react";
import Card from "../components/common/Card";
import Button from "../components/common/Button";
import ErrorBoundary from "../components/common/ErrorBoundary";
import { reportError } from "../utils/helpers";
import { useAuth, useNotifications } from "../utils/hooks/useSupabase";
import supabase from "../utils/supabaseClient";

function Notifications() {
    const { user: authUser, isAuthenticated } = useAuth();
    const { notifications, loading, error, markAsRead, unreadCount } = useNotifications(authUser?.id);

    // Auth redirect is handled by ProtectedRoute wrapper in app.jsx
    // No need for manual redirect here

    const handleMarkAsRead = async (notificationId) => {
        try {
            await markAsRead(notificationId);
        } catch (error) {
            console.error('Error marking notification as read:', error);
            reportError(error);
        }
    };

    const markAllAsRead = async () => {
        try {
            const unread = notifications.filter(n => !n.read);
            await Promise.all(unread.map(n => markAsRead(n.id)));
        } catch (error) {
            console.error('Error marking all as read:', error);
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
            const { error } = await supabase
                .from('notifications')
                .delete()
                .eq('id', notificationId);
            if (error) throw error;
            // Realtime subscription handles removing from local state
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
            <div className="min-h-screen bg-gradient-to-b from-[#2CABE3]/5 via-white to-emerald-50/40" role="main" aria-labelledby="notifications-title">
                {/* Hero */}
                <header className="relative overflow-hidden">
                    <div className="absolute inset-0 -z-10" aria-hidden="true">
                        <div className="absolute -top-24 -left-24 w-96 h-96 rounded-full bg-[#2CABE3]/15 blur-3xl" />
                        <div className="absolute top-10 -right-24 w-96 h-96 rounded-full bg-emerald-300/20 blur-3xl" />
                    </div>
                    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-12 sm:pt-20 sm:pb-16">
                        <div className="text-center">
                            <span className="inline-flex items-center px-3 py-1 rounded-full bg-[#2CABE3]/10 text-[#2CABE3] text-xs font-semibold mb-5 ring-1 ring-[#2CABE3]/20">
                                <i className="fas fa-bell mr-2" aria-hidden="true"></i>
                                Activity
                            </span>
                            <h1 id="notifications-title" className="text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-900 mb-5 tracking-tight">
                                Your{" "}
                                <span className="bg-gradient-to-r from-[#2CABE3] to-emerald-500 bg-clip-text text-transparent">
                                    Notifications
                                </span>
                            </h1>
                            <p className="text-base sm:text-lg text-gray-600 max-w-2xl mx-auto leading-relaxed">
                                Recent updates about your claims, listings, and community activity.
                            </p>
                        </div>
                    </div>
                </header>

                <main className="max-w-4xl mx-auto py-2 px-4 pb-10">
                <div className="flex justify-end items-center mb-8">
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
                                    notification.read ? 'bg-white' : 'bg-primary-50'
                                }`}
                                role="article"
                                aria-labelledby={`notification-${notification.id}-title`}
                            >
                                <div className="p-4">
                                    <div className="flex items-start">
                                        <div className="flex-shrink-0">
                                            <div 
                                                className="w-10 h-10 bg-primary-100 rounded-full flex items-center justify-center"
                                                aria-hidden="true"
                                            >
                                                <i className={`fas ${getNotificationIcon(notification.type)} text-primary-600`}></i>
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
                                                        dateTime={notification.created_at}
                                                    >
                                                        {notification.created_at ? new Date(notification.created_at).toLocaleString() : ''}
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
            </div>
        </ErrorBoundary>
    );
}

export default Notifications;
