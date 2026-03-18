import { useState } from 'react';
import { ConnectionForm } from './components/ConnectionForm';
import { QueryChatPage } from './components/QueryChatPage';
import {
  SignedIn,
  SignedOut,
  SignInButton,
  SignUpButton,
  UserButton,
} from '@clerk/clerk-react';

type AppPage = 'connect' | 'query';

function App() {
  const [page, setPage] = useState<AppPage>('connect');
  const [activeConnectionProfileId, setActiveConnectionProfileId] = useState<string | null>(null);
  const [activeConnectionExpiresAtMs, setActiveConnectionExpiresAtMs] = useState<number | null>(null);

  const handleConnectionSuccess = (profileId: string, expiresAtMs: number) => {
    setActiveConnectionProfileId(profileId);
    setActiveConnectionExpiresAtMs(expiresAtMs);
    setPage('query');
  };

  const goToConnectPage = () => {
    setPage('connect');
  };

  return (
    <div className="min-h-screen w-full flex flex-col bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900 via-[#0a0a0a] to-black">
      {/* Header */}
      <header className="relative z-20 w-full p-4 flex justify-between items-center shrink-0">
        <h1 className="text-xl font-bold bg-gradient-to-br from-white to-white/60 bg-clip-text text-transparent">
          SequelSpeak
        </h1>
        <div className="flex items-center gap-3">
          <SignedOut>
            <SignInButton mode="modal">
              <button className="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 text-white text-sm font-medium transition-colors border border-white/10">
                Sign In
              </button>
            </SignInButton>
            <SignUpButton mode="modal">
              <button className="px-4 py-2 rounded-lg bg-gradient-to-r from-primary to-secondary hover:opacity-90 text-white text-sm font-medium transition-opacity">
                Sign Up
              </button>
            </SignUpButton>
          </SignedOut>
          <SignedIn>
            <UserButton />
          </SignedIn>
        </div>
      </header>

      {/* Background decoration */}
      <div className="absolute top-0 left-0 w-full h-full overflow-hidden pointer-events-none z-0">
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] rounded-full bg-primary/20 blur-[128px]" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] rounded-full bg-secondary/20 blur-[128px]" />
      </div>

      {/* Main Content */}
      <div className="relative z-10 flex-1 w-full flex items-start justify-center p-4 overflow-hidden">
        <SignedIn>
          {page === 'connect' && (
            <div className="w-full max-w-4xl">
              <ConnectionForm onConnectionSuccess={handleConnectionSuccess} />
            </div>
          )}

          {page === 'query' && activeConnectionProfileId && (
            <div className="w-full max-w-4xl flex flex-col" style={{ height: 'calc(100vh - 7rem)' }}>
              <QueryChatPage
                activeConnectionProfileId={activeConnectionProfileId}
                activeConnectionExpiresAtMs={activeConnectionExpiresAtMs}
                onConnectionActivated={handleConnectionSuccess}
                onGoToConnect={goToConnectPage}
                className="flex-1 min-h-0 rounded-2xl border border-white/10 bg-white/5 backdrop-blur-sm overflow-hidden"
              />
            </div>
          )}
        </SignedIn>

        <SignedOut>
          <div className="text-center space-y-4 max-w-4xl w-full">
            <h2 className="text-2xl font-bold bg-gradient-to-br from-white to-white/60 bg-clip-text text-transparent">
              Welcome to SequelSpeak
            </h2>
            <p className="text-gray-400">
              Please sign in to connect to your database
            </p>
          </div>
        </SignedOut>
      </div>
    </div>
  );
}

export default App;
