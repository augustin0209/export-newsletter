from django import forms
from .models import Newsletter, Subscriber
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

class NewsletterForm(forms.ModelForm):
    contenu_text = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 10, 'class': 'form-control'}),
        required=True,
        label='Contenu'
    )

    class Meta:
        model = Newsletter
        fields = ['titre', 'objet', 'contenu_text', 'police']
        widgets = {
            'titre': forms.TextInput(attrs={'class': 'form-control'}),
            'objet': forms.TextInput(attrs={'class': 'form-control'}),
            'police': forms.TextInput(attrs={'class': 'form-control', 'value': 'Arial'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        contenu_text = cleaned_data.get('contenu_text')

        # Si aucun des deux champs n'est rempli, lever une erreur
        if not contenu_text:
            raise forms.ValidationError("Vous devez remplir le champ de contenu.")

        return cleaned_data

class SubscriberForm(forms.ModelForm):
    class Meta:
        model = Subscriber
        fields = ['email', 'nom', 'prenom']
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'nom': forms.TextInput(attrs={'class': 'form-control'}),
            'prenom': forms.TextInput(attrs={'class': 'form-control'}),
        }

class ImportSubscribersForm(forms.Form):
    file = forms.FileField(
        label='Fichier CSV ou Excel',
        help_text='Formats acceptés : CSV, XLS, XLSX',
        widget=forms.FileInput(attrs={'class': 'form-control'})
    )
    email_column = forms.CharField(
        label='Colonne email',
        initial='email',
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    nom_column = forms.CharField(
        label='Colonne nom',
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    prenom_column = forms.CharField(
        label='Colonne prénom',
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

class CustomLoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': "Nom d'utilisateur"
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Mot de passe'
        })
    ) 