import React, { useId } from 'react';
import PropTypes from 'prop-types';
import { reportError } from '../../utils/helpers';

const INPUT_TYPES = ['text', 'email', 'password', 'number', 'tel', 'url', 'search', 'date', 'time', 'datetime-local', 'month', 'week', 'textarea', 'select', 'file'];

const Input = ({ label, value, onChange, disabled, className, type = "text", ...props }) => {
    if (!INPUT_TYPES.includes(type)) {
        console.warn(`Invalid input type: ${type}. Falling back to 'text'`);
        type = 'text';
    }

    const inputId = useId();
    const errorId = props.error ? `${inputId}-error` : undefined;
    const helperId = props.helperText ? `${inputId}-helper` : undefined;
    const descriptionId = props['aria-describedby'] || errorId || helperId;

    const baseInputStyles = `
        w-full px-4 py-2 rounded-lg border
        focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent
        disabled:bg-gray-100 disabled:cursor-not-allowed
        transition-colors duration-200
    `;

    const inputStyles = `
        ${baseInputStyles}
        ${props.error ? 'border-red-500' : 'border-gray-300'}
        ${props.icon ? 'pl-10' : ''}
        ${className}
    `.trim().replace(/\s+/g, ' ');

    const renderInput = () => {
        const commonProps = {
            id: inputId,
            name: props.name,
            disabled,
            required: props.required,
            'aria-invalid': props.error ? 'true' : 'false',
            'aria-describedby': descriptionId,
            className: inputStyles,
            autoComplete: props.autoComplete
        };

        switch (type) {
            case 'textarea':
                return (
                    <textarea
                        {...commonProps}
                        value={value}
                        onChange={onChange}
                        placeholder={props.placeholder}
                        rows={props.rows}
                    />
                );
            case 'select':
                if (!props.options.length) {
                    console.warn('Select input rendered without options');
                }
                return (
                    <select
                        {...commonProps}
                        value={value}
                        onChange={onChange}
                    >
                        {props.options.map((option, index) => (
                            <option 
                                key={option.value || index} 
                                value={option.value}
                                disabled={option.disabled}
                            >
                                {option.label}
                            </option>
                        ))}
                    </select>
                );
            case 'file':
                return (
                    <input
                        {...commonProps}
                        type={type}
                        onChange={onChange}
                        accept={props.accept}
                        className={`${inputStyles} file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-green-50 file:text-green-700 hover:file:bg-green-100`}
                        multiple={props.accept?.includes('multiple')}
                    />
                );
            default:
                return (
                    <input
                        {...commonProps}
                        type={type}
                        value={value}
                        onChange={onChange}
                        placeholder={props.placeholder}
                        min={props.min}
                        max={props.max}
                    />
                );
        }
    };

    return (
        <div 
            data-name="input-wrapper" 
            className="w-full"
            role={type === 'select' ? 'group' : undefined}
        >
            {label && (
                <label
                    htmlFor={inputId}
                    className="block text-sm font-medium text-gray-700 mb-1"
                >
                    {label}
                    {props.required && (
                        <span className="text-red-500 ml-1" aria-hidden="true">*</span>
                    )}
                    {props.required && (
                        <span className="sr-only">(Required)</span>
                    )}
                </label>
            )}

            <div className="relative">
                {props.icon && (
                    <div 
                        className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-gray-400"
                        aria-hidden="true"
                    >
                        {props.icon}
                    </div>
                )}

                {renderInput()}
            </div>

            {(props.error || props.helperText) && (
                <p 
                    id={props.error ? errorId : helperId}
                    className={`mt-1 text-sm ${props.error ? 'text-red-500' : 'text-gray-500'}`}
                    role={props.error ? 'alert' : 'status'}
                >
                    {props.error || props.helperText}
                </p>
            )}
        </div>
    );
};

Input.propTypes = {
    type: PropTypes.oneOf(INPUT_TYPES),
    label: PropTypes.string,
    value: PropTypes.oneOfType([
        PropTypes.string,
        PropTypes.number,
        PropTypes.arrayOf(PropTypes.string) // for multiple file inputs
    ]),
    onChange: PropTypes.func.isRequired,
    placeholder: PropTypes.string,
    error: PropTypes.string,
    helperText: PropTypes.string,
    required: PropTypes.bool,
    disabled: PropTypes.bool,
    icon: PropTypes.node,
    className: PropTypes.string,
    options: PropTypes.arrayOf(
        PropTypes.shape({
            value: PropTypes.oneOfType([PropTypes.string, PropTypes.number]).isRequired,
            label: PropTypes.string.isRequired,
            disabled: PropTypes.bool
        })
    ),
    min: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
    max: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
    accept: PropTypes.string,
    rows: PropTypes.number,
    name: PropTypes.string,
    autoComplete: PropTypes.string,
    'aria-describedby': PropTypes.string
};

export { Input };
export default Input;
