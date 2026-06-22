import React, { forwardRef } from 'react';
import styles from './Input.module.css';

const Input = forwardRef(({
  label,
  error,
  required = false,
  className = '',
  icon: Icon,
  ...props
}, ref) => {
  const inputClass = `${styles.input} ${error ? styles.errorInput : ''} ${Icon ? styles.withIcon : ''}`;
  
  return (
    <div className={`${styles.container} ${className}`}>
      {label && (
        <label className={styles.label}>
          {label}
          {required && <span className={styles.required}>*</span>}
        </label>
      )}
      <div className={styles.inputWrapper}>
        {Icon && <Icon size={18} className={styles.icon} />}
        <input 
          ref={ref}
          className={inputClass}
          aria-invalid={!!error}
          {...props}
        />
      </div>
      {error && <span className={styles.errorMessage}>{error}</span>}
    </div>
  );
});

Input.displayName = 'Input';

export default Input;
