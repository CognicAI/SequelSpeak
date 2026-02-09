import { ConnectionForm } from './components/ConnectionForm';
import { ExpandableChatDemo } from './components/ExpandableChatDemo';
import {
  SignedIn,
  SignedOut,
  SignInButton,
  SignUpButton,
  UserButton,
} from '@clerk/clerk-react';

function App() {
  return (
    <div className="min-h-screen w-full flex flex-col bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900 via-[#0a0a0a] to-black">
      {/* Header with Auth */}
      <header className="relative z-20 w-full p-4 flex justify-between items-center">
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

      {/* Main Content */}
      <div className="flex-1 w-full flex items-center justify-center p-4">
        {/* Background decoration */}
        <div className="absolute top-0 left-0 w-full h-full overflow-hidden pointer-events-none z-0">
          <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] rounded-full bg-primary/20 blur-[128px]" />
          <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] rounded-full bg-secondary/20 blur-[128px]" />
        </div>

        <div className="relative z-10 w-full max-w-4xl">
          <SignedIn>
            <ConnectionForm />
          </SignedIn>
          <SignedOut>
            <div className="text-center space-y-4">
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

      {/* AI Chat Assistant - Only visible when signed in */}
      <SignedIn>
        <ExpandableChatDemo />
      </SignedIn>
    </div>
  );
}

export default App;
