// PaperFull — Login / Register screen. Recreated from frontend/src/views/LoginPage.vue
const { useState: useLoginState } = React;

function GoogleG() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
    </svg>
  );
}

function Login({ onBack, onAuthed }) {
  const [isRegister, setIsRegister] = useLoginState(false);
  return (
    <div className="mk">
      <div className="login-wrap">
        <div className="login">
          <div className="login-head">
            <img src="../../assets/logo-with-text.png" alt="PaperFull" />
            <p>AI-powered academic paper writing tool</p>
          </div>
          <div className="login-card">
            <h2>{isRegister ? 'Create an account' : 'Sign in to your account'}</h2>
            <p className="sub">{isRegister ? 'Register with your email to get started' : 'Use your email or Google account'}</p>

            <form onSubmit={(e) => { e.preventDefault(); onAuthed(); }}>
              {isRegister && (
                <div className="field">
                  <label>Name <span className="req">*</span></label>
                  <input type="text" placeholder="Your full name" />
                </div>
              )}
              <div className="field">
                <label>Email <span className="req">*</span></label>
                <input type="email" placeholder="you@example.com" />
              </div>
              <div className="field">
                <label>Password <span className="req">*</span></label>
                <input type="password" placeholder="Min. 8 chars, mix of types" />
              </div>
              <button className="btn-submit" type="submit">{isRegister ? 'Create Account' : 'Sign In'}</button>
            </form>

            <div className="divider"><div className="ln"></div><span>or</span><div className="ln"></div></div>

            <button className="btn-google" onClick={onAuthed}><GoogleG /> Continue with Google</button>

            <p className="login-toggle">
              {isRegister ? 'Already have an account?' : "Don't have an account?"}
              <button onClick={() => setIsRegister(!isRegister)}>{isRegister ? ' Sign In' : ' Register'}</button>
            </p>
            <p className="login-fine">By signing in, you agree to our privacy policy.<br/>Your papers are private and belong to you.</p>
          </div>
          <div className="login-back"><button onClick={onBack}>← Back to home</button></div>
        </div>
      </div>
    </div>
  );
}

window.Login = Login;
