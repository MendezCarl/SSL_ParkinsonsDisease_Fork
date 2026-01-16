import { useState, useEffect } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import { ArrowLeft, Save, User, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/hooks/use-toast';
import { Patient } from '@/types/patient';
import apiService, { normalizeBirthDate } from '@/services/api';

const PatientForm = () => {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const { toast } = useToast();
  const isEditing = !!id;

  const [formData, setFormData] = useState({
    firstName: '',
    lastName: '',
    recordNumber: '',
    birthDate: '',
    height: '',
    weight: '',
    labResults: '',
    doctorNotes: '',
    severity: '' as Patient['severity'],
  });
  const [loading, setLoading] = useState(false);

  const handleInputChange = (field: string, value: string) => {
    if (field === 'birthDate') {
      const normalized = normalizeBirthDate(value);
      setFormData(prev => ({ ...prev, [field]: normalized || value }));
      return;
    }
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  // Load patient data if editing
  useEffect(() => {
    if (isEditing && id) {
      loadPatientData();
    }
  }, [isEditing, id]);

  const loadPatientData = async () => {
    try {
      const response = await apiService.getPatient(id!);
      if (response.success && response.data) {
        const patient = response.data;
        setFormData({
          firstName: patient.firstName,
          lastName: patient.lastName,
          recordNumber: patient.recordNumber,
          birthDate: normalizeBirthDate(patient.birthDate) || patient.birthDate.toString(),
          height: patient.height,
          weight: patient.weight,
          labResults: patient.labResults,
          doctorNotes: patient.doctorNotes,
          severity: patient.severity,
        });
      }
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to load patient data",
        variant: "destructive",
      });
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    if (!formData.firstName || !formData.lastName || !formData.recordNumber || !formData.birthDate || !formData.severity) {
      toast({
        title: "Validation Error",
        description: "Please fill in all required fields.",
        variant: "destructive",
      });
      setLoading(false);
      return;
    }

    try {
      const normalizedBirthDate = normalizeBirthDate(formData.birthDate);
      if (!normalizedBirthDate) {
        toast({
          title: "Invalid Birthdate",
          description: "Enter a valid date (e.g., 1980-05-12 or 05/12/1980).",
          variant: "destructive",
        });
        setLoading(false);
        return;
      }

      const patientData = {
        firstName: formData.firstName,
        lastName: formData.lastName,
        recordNumber: formData.recordNumber,
        birthDate: normalizedBirthDate,
        height: formData.height || '170 cm',
        weight: formData.weight || '70 kg',
        labResults: formData.labResults || '{}',
        doctorNotes: formData.doctorNotes || '',
        severity: formData.severity,
        createdAt: new Date(),
        updatedAt: new Date(),
      };

      console.log('Saving patient with data:', patientData);
      console.log('Is editing:', isEditing, 'ID:', id);

      let response;
      if (isEditing && id) {
        response = await apiService.updatePatient(id, patientData);
      } else {
        response = await apiService.createPatient(patientData);
      }
      
      console.log('API response:', response);

      if (response.success) {
        toast({
          title: isEditing ? "Patient Updated" : "Patient Created",
          description: `${formData.firstName} ${formData.lastName} has been ${isEditing ? 'updated' : 'added'} successfully.`,
        });
        navigate(isEditing ? `/patient/${id}` : '/');
      } else {
        toast({
          title: "Error",
          description: response.error || "Failed to save patient",
          variant: "destructive",
        });
      }
    } catch (error) {
      console.error("Submission error:", error);
      toast({
        title: "Error",
        description: "Failed to connect to the server",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };



  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b bg-card shadow-card">
        <div className="container mx-auto px-6 py-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <Link to={isEditing ? `/patient/${id}` : '/'}>
                <Button variant="outline" size="sm">
                  <ArrowLeft className="mr-2 h-4 w-4" />
                  {isEditing ? 'Back to Patient' : 'Back to Patients'}
                </Button>
              </Link>
              <div>
                <h1 className="text-3xl font-bold text-foreground">
                  {isEditing ? 'Edit Patient' : 'Add New Patient'}
                </h1>
                <p className="text-muted-foreground mt-1">
                  {isEditing ? 'Update patient information' : 'Enter patient details to create a new record'}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Form */}
      <div className="container mx-auto px-6 py-8">
        <div className="max-w-2xl mx-auto">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center">
                <User className="mr-2 h-5 w-5" />
                Patient Information
              </CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-6">
                {/* Basic Information */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="space-y-2">
                    <Label htmlFor="firstName">First Name *</Label>
                    <Input
                      id="firstName"
                      placeholder="Enter first name"
                      value={formData.firstName}
                      onChange={(e) => handleInputChange('firstName', e.target.value)}
                      required
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="lastName">Last Name *</Label>
                    <Input
                      id="lastName"
                      placeholder="Enter last name"
                      value={formData.lastName}
                      onChange={(e) => handleInputChange('lastName', e.target.value)}
                      required
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="recordNumber">Record Number *</Label>
                    <Input
                      id="recordNumber"
                      placeholder="e.g., P001"
                      value={formData.recordNumber}
                      onChange={(e) => handleInputChange('recordNumber', e.target.value)}
                      required
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="birthDate">Birthdate *</Label>
                    <Input
                      id="birthDate"
                      type="date"
                      placeholder="YYYY-MM-DD"
                      value={formData.birthDate}
                      onChange={(e) => handleInputChange('birthDate', e.target.value)}
                      required
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="height">Height</Label>
                    <Input
                      id="height"
                      placeholder="e.g., 5'8&quot;"
                      value={formData.height}
                      onChange={(e) => handleInputChange('height', e.target.value)}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="weight">Weight</Label>
                    <Input
                      id="weight"
                      placeholder="e.g., 170 lbs"
                      value={formData.weight}
                      onChange={(e) => handleInputChange('weight', e.target.value)}
                    />
                  </div>
                </div>

                {/* Severity */}
                <div className="space-y-2">
                  <Label htmlFor="severity">Parkinson's Severity *</Label>
                  <Select value={formData.severity} onValueChange={(value) => handleInputChange('severity', value)}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select severity level" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Stage 1">Stage 1</SelectItem>
                      <SelectItem value="Stage 2">Stage 2</SelectItem>
                      <SelectItem value="Stage 3">Stage 3</SelectItem>
                      <SelectItem value="Stage 4">Stage 4</SelectItem>
                      <SelectItem value="Stage 5">Stage 5</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* Lab Results */}
                <div className="space-y-2">
                  <Label htmlFor="labResults">Lab Results</Label>
                  <Textarea
                    id="labResults"
                    placeholder="Enter lab results and findings..."
                    value={formData.labResults}
                    onChange={(e) => handleInputChange('labResults', e.target.value)}
                    rows={3}
                  />
                </div>

                {/* Doctor's Notes */}
                <div className="space-y-2">
                  <Label htmlFor="doctorNotes">Doctor's Notes</Label>
                  <Textarea
                    id="doctorNotes"
                    placeholder="Enter clinical observations, treatment notes, etc..."
                    value={formData.doctorNotes}
                    onChange={(e) => handleInputChange('doctorNotes', e.target.value)}
                    rows={4}
                  />
                </div>

                {/* Submit Button */}
                <div className="flex justify-end space-x-4 pt-6">
                  <Link to={isEditing ? `/patient/${id}` : '/'}>
                    <Button variant="outline" disabled={loading}>
                      Cancel
                    </Button>
                  </Link>
                  <Button type="submit" className="bg-primary hover:bg-primary-hover text-primary-foreground" disabled={loading}>
                    {loading ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <Save className="mr-2 h-4 w-4" />
                    )}
                    {loading ? 'Saving...' : (isEditing ? 'Update Patient' : 'Create Patient')}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default PatientForm;