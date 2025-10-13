import React from "react";
import Header from "../common/Header";
import Footer from "../common/Footer";
import AssistantButton from "../assistant/AssistantButton";
import AIAssistant from "../assistant/AIAssistant";
import SponsoredBy from "../common/SponsoredBy";


function MainLayout({ children }) {
    const [isAssistantOpen, setIsAssistantOpen] = React.useState(false);
    
    const toggleAssistant = () => {
        setIsAssistantOpen(!isAssistantOpen);
    };
    
    return (
        <div data-name="main-layout" className="min-h-screen flex flex-col bg-gradient-to-br from-green-50 via-white to-green-100">
            <Header/>
            <main className="flex-grow container mx-auto px-4 py-8">
                <div className="rounded-3xl shadow-2xl bg-white/80 backdrop-blur-md border border-green-100 p-6 md:p-10 transition-all duration-300">
                    {children}
                    <SponsoredBy />
                </div>
            </main>
            <Footer />
            
            {/* AI Assistant Button and Modal */}
            <AssistantButton onClick={toggleAssistant} />
            {isAssistantOpen && (
                <AIAssistant 
                    key="ai-assistant"
                    isOpen={isAssistantOpen} 
                    onClose={() => setIsAssistantOpen(false)} 
                />
            )}
        </div>
    );
}


export default MainLayout;
