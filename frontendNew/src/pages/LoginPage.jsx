import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Lock, Mail, ArrowRight } from 'lucide-react';
import { motion } from 'framer-motion';
import styles from './LoginPage.module.css';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';

const LoginPage = () => {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const handleLogin = (e) => {
    e.preventDefault();
    setError('');

    // Basic validation to fix UX audit finding
    if (!email.includes('@')) {
      setError('Please enter a valid email address.');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters long.');
      return;
    }

    setIsLoading(true);
    // Simulate API call
    setTimeout(() => {
      setIsLoading(false);
      navigate('/dashboard');
    }, 1500);
  };

  return (
    <div className={styles.container}>
      <div className={styles.leftPanel}>
        <motion.div 
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className={styles.brandContainer}
        >
          <div className={styles.logoBox}>P</div>
          <h1 className={styles.brandTitle}>PaperFull</h1>
          <p className={styles.brandSubtitle}>
            Accelerate your academic research with AI-powered drafting, management, and publishing.
          </p>
        </motion.div>
      </div>

      <div className={styles.rightPanel}>
        <motion.div 
          className={styles.loginCard}
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.4, delay: 0.2 }}
        >
          <div className={styles.loginHeader}>
            <h2>Welcome back</h2>
            <p>Enter your credentials to access your workspace.</p>
          </div>

          <form onSubmit={handleLogin} className={styles.form}>
            <Input 
              label="Email Address" 
              type="email" 
              placeholder="name@university.edu" 
              icon={Mail}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            
            <div className={styles.passwordGroup}>
              <Input 
                label="Password" 
                type="password" 
                placeholder="••••••••" 
                icon={Lock}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              <a href="#" className={styles.forgotLink}>Forgot password?</a>
            </div>

            {error && <div className={styles.errorAlert}>{error}</div>}

            <Button 
              type="submit" 
              className={styles.submitBtn} 
              loading={isLoading}
              icon={ArrowRight}
            >
              Sign In
            </Button>
          </form>

          <div className={styles.footer}>
            Don't have an account? <a href="#">Request access</a>
          </div>
        </motion.div>
      </div>
    </div>
  );
};

export default LoginPage;
