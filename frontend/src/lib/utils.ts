import { Patient } from "@/types/patient";
import { clsx, type ClassValue } from "clsx"
import { parse } from "path";
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export const getSeverityColor = (severity: Patient['severity']) => {
    switch (severity) {
      case 'Stage 1':
        return 'bg-success text-success-foreground';
      case 'Stage 2':
        return 'bg-warning text-warning-foreground';
      case 'Stage 3':
        return 'bg-orange-500 text-white';
      case 'Stage 4':
        return 'bg-destructive text-destructive-foreground';
      case 'Stage 5':
        return 'bg-red-900 text-white';
      default:
        return 'bg-muted text-muted-foreground';
    }
  };

export const calculateAge = (birthdate: Patient['birthDate']) => {
  // yyyy-mm-dd
  if (!birthdate || typeof birthdate !== 'string') {
    return 0;
  }
  
  try {
    const [year, month, day] = birthdate.split('-').map(Number);
    
    // Validate that we got valid numbers
    if (isNaN(year) || isNaN(month) || isNaN(day)) {
      return 0;
    }
    
    const today = new Date();
    let age = today.getFullYear() - year;

    // Check if birthday hasn't occurred yet this year
    if(
      today.getMonth() + 1 < month ||
      (today.getMonth() + 1 === month && today.getDate() < day)
    ){
      age--
    }

    return age >= 0 ? age : 0;
  } catch (error) {
    console.error("Invalid birthdate format:", error);
    return 0;
  }
}