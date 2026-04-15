import { useState, useEffect, useCallback } from 'react';
import {
  Autocomplete,
  TextField,
  Chip,
  Box,
  Typography,
  CircularProgress,
} from '@mui/material';
import { Person as PersonIcon } from '@mui/icons-material';
import axios from 'axios';

interface Contact {
  name: string;
  email: string;
  organization?: string | null;
}

interface RecipientAutocompleteProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  placeholder?: string;
}

/**
 * Email recipient input with contact autocomplete.
 *
 * Allows users to:
 * - Type email addresses manually (comma-separated)
 * - Search and select from contacts as they type
 * - Add multiple recipients as chips
 */
export default function RecipientAutocomplete({
  label,
  value,
  onChange,
  onBlur,
  placeholder = 'recipient@example.com',
}: RecipientAutocompleteProps) {
  const [inputValue, setInputValue] = useState('');
  const [options, setOptions] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(false);

  // Parse comma-separated emails into array
  const parseEmails = (emailString: string): string[] => {
    return emailString
      .split(',')
      .map(email => email.trim())
      .filter(email => email.length > 0);
  };

  // Convert array back to comma-separated string
  const toEmailString = (emails: string[]): string => {
    return emails.join(', ');
  };

  // Current recipients as array
  const recipients = parseEmails(value);

  // Debounced contact search
  useEffect(() => {
    if (inputValue.length < 2) {
      setOptions([]);
      return;
    }

    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const response = await axios.get('/api/contacts/search', {
          params: { q: inputValue },
        });
        setOptions(response.data.contacts || []);
      } catch (err) {
        console.error('Contact search failed:', err);
        setOptions([]);
      } finally {
        setLoading(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [inputValue]);

  // Handle selection from autocomplete
  const handleChange = useCallback(
    (_event: React.SyntheticEvent, newValue: (string | Contact)[]) => {
      // Convert contacts to emails, keep raw strings as-is
      const emails = newValue.map(item =>
        typeof item === 'string' ? item : item.email
      );
      onChange(toEmailString(emails));
    },
    [onChange]
  );

  // Commit whatever's in the input as a recipient
  const commitInput = useCallback(
    (raw: string) => {
      const email = raw.trim().replace(/,+$/, '').trim();
      if (email.length > 0 && !recipients.map(r => r.toLowerCase()).includes(email.toLowerCase())) {
        onChange(toEmailString([...recipients, email]));
      }
      setInputValue('');
    },
    [recipients, onChange]
  );

  // Handle input change (typing) — commit on comma/semicolon
  const handleInputChange = useCallback(
    (_event: React.SyntheticEvent, newInputValue: string) => {
      if (newInputValue.includes(',') || newInputValue.includes(';')) {
        commitInput(newInputValue.replace(/[,;]/g, ''));
      } else {
        setInputValue(newInputValue);
      }
    },
    [commitInput]
  );

  // Render option with contact details
  const renderOption = (
    props: React.HTMLAttributes<HTMLLIElement> & { key?: string },
    option: string | Contact
  ) => {
    const { key, ...otherProps } = props;
    if (typeof option === 'string') {
      return (
        <li key={key} {...otherProps}>
          <Typography>{option}</Typography>
        </li>
      );
    }

    return (
      <li key={key} {...otherProps}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <PersonIcon fontSize="small" color="action" />
          <Box>
            <Typography variant="body2">{option.name}</Typography>
            <Typography variant="caption" color="text.secondary">
              {option.email}
              {option.organization && ` • ${option.organization}`}
            </Typography>
          </Box>
        </Box>
      </li>
    );
  };

  // Get display label for chip
  const getOptionLabel = (option: string | Contact): string => {
    if (typeof option === 'string') return option;
    return option.email;
  };

  // Check if option equals value (for selection tracking)
  const isOptionEqualToValue = (option: string | Contact, value: string | Contact): boolean => {
    const optionEmail = typeof option === 'string' ? option : option.email;
    const valueEmail = typeof value === 'string' ? value : value.email;
    return optionEmail.toLowerCase() === valueEmail.toLowerCase();
  };

  // Filter options to exclude already-selected recipients
  const filterOptions = (options: Contact[]): Contact[] => {
    const selectedEmails = recipients.map(e => e.toLowerCase());
    return options.filter(opt => !selectedEmails.includes(opt.email.toLowerCase()));
  };

  return (
    <Autocomplete
      multiple
      freeSolo
      options={filterOptions(options)}
      value={recipients}
      onChange={handleChange}
      inputValue={inputValue}
      onInputChange={handleInputChange}
      getOptionLabel={getOptionLabel}
      isOptionEqualToValue={isOptionEqualToValue}
      renderOption={renderOption}
      loading={loading}
      filterOptions={(x) => x} // Disable client-side filtering (server does it)
      renderTags={(value, getTagProps) =>
        value.map((option, index) => {
          const { key, ...tagProps } = getTagProps({ index });
          return (
            <Chip
              key={key}
              label={typeof option === 'string' ? option : option.email}
              size="small"
              {...tagProps}
            />
          );
        })
      }
      renderInput={(params) => (
        <TextField
          {...params}
          label={label}
          placeholder={recipients.length === 0 ? placeholder : ''}
          onBlur={() => {
            if (inputValue.trim()) commitInput(inputValue);
            onBlur?.();
          }}
          InputProps={{
            ...params.InputProps,
            endAdornment: (
              <>
                {loading && <CircularProgress color="inherit" size={20} />}
                {params.InputProps.endAdornment}
              </>
            ),
          }}
        />
      )}
      sx={{ mb: 2 }}
    />
  );
}
