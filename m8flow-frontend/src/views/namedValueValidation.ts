export const validateNamedValueName = (name: string): string => {
  const normalizedName = name.trim();
  if (
    !normalizedName
    || normalizedName.length > 255
    || !/^[\w-]+$/.test(normalizedName)
  ) {
    return 'The name must contain only letters, numbers, underscores, and hyphens, and be 1-255 characters long.';
  }
  return '';
};
