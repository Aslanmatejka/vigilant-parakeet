import React from "react";
import Header from "../common/Header";
import Footer from "../common/Footer";
import AIChatPanel from "../assistant/AIChatPanel";
import UserChatWidget from "../common/UserChatWidget";
import Tutorial from "../common/Tutorial";
import AIHealthBanner from "../common/AIHealthBanner";
import { useTutorial } from "../../utils/TutorialContext";
import { useAuthContext } from "../../utils/AuthContext";
import receiptService from "../../utils/receiptService";

// Module-level flag — survives re-mounts but resets on full page reload
let tutorialAutoStartChecked = false;
let receiptExpiryChecked = false;


function MainLayout({ children }) {
    // const [isAssistantOpen, setIsAssistantOpen] = React.useState(false);

    // const toggleAssistant = () => {
    //     setIsAssistantOpen(!isAssistantOpen);
    // };

    const { isTutorialOpen, startTutorial } = useTutorial();
    const { isAuthenticated } = useAuthContext();

    // Auto-start tutorial ONLY for first-time visitors.
    // Fires once per full page load; localStorage check prevents repeat visits.
    React.useEffect(() => {
        if (tutorialAutoStartChecked) return;
        tutorialAutoStartChecked = true;

        const alreadyCompleted = localStorage.getItem('dogoods_tutorial_completed') === 'true';
        if (!alreadyCompleted) {
            const timer = setTimeout(() => {
                startTutorial();
            }, 1500);
            return () => clearTimeout(timer);
        }
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    // Best-effort: once per page load, ask the DB to expire any receipts whose
    // pickup_by has passed. This ensures receipts get marked expired even if
    // the user never opens the Receipts page after the Friday deadline.
    React.useEffect(() => {
        if (!isAuthenticated || receiptExpiryChecked) return;
        receiptExpiryChecked = true;
        receiptService.expireOldReceipts().catch(() => {
            // Silent — best-effort background task.
        });
    }, [isAuthenticated]);

    return (
        <div data-name="main-layout" className="min-h-screen flex flex-col bg-gradient-to-br from-cyan-50 via-white to-cyan-100">
            <Header/>
            <main className="flex-grow container mx-auto px-2 sm:px-4 py-3 sm:py-8">
                <div className="rounded-xl sm:rounded-3xl shadow-lg sm:shadow-2xl bg-white/80 backdrop-blur-md border border-cyan-100 p-3.5 sm:p-6 md:p-10 transition-all duration-300">
                    {children}
                </div>
            </main>
            <Footer />

            {/* Nouri AI Assistant */}
            <AIChatPanel />

            {/* User Chat Widget (for messaging admin) */}
            <UserChatWidget />

            {/* Global Tutorial Overlay */}
            <Tutorial />

            {/* AI Self-Healing Status Banner */}
            <AIHealthBanner />
        </div>
    );
}


export default MainLayout;
