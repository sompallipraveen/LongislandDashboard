/**
 * Admin Dashboard JavaScript File
 * Long Island Perfumes Admin Panel
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize all tooltips
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    const tooltipList = [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));
    
    // Initialize all popovers
    const popoverTriggerList = document.querySelectorAll('[data-bs-toggle="popover"]');
    const popoverList = [...popoverTriggerList].map(popoverTriggerEl => new bootstrap.Popover(popoverTriggerEl));
    
    // Mobile sidebar toggle
    const sidebarToggle = document.getElementById('sidebarToggleTop');
    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', function() {
            document.body.classList.toggle('sidebar-toggled');
            document.getElementById('sidebar').classList.toggle('toggled');
        });
    }
    
    // Close any open menu when window is resized
    window.addEventListener('resize', function() {
        const windowWidth = window.innerWidth;
        if (windowWidth < 768) {
            document.getElementById('sidebar').classList.add('toggled');
        } else {
            document.getElementById('sidebar').classList.remove('toggled');
        }
    });
    
    // Prevent the content wrapper from scrolling when the fixed side navigation hovered over
    document.querySelector('body.fixed-nav .sidebar').onmousewheel = function(e) {
        if (this.scrollTop === 0 && e.deltaY < 0) {
            e.preventDefault();
        } else if (this.scrollHeight - this.scrollTop <= this.clientHeight && e.deltaY > 0) {
            e.preventDefault();
        }
    };
    
    // Handle quantity input controls
    const quantityInputs = document.querySelectorAll('.quantity-input');
    if (quantityInputs.length > 0) {
        quantityInputs.forEach(input => {
            const decrementBtn = input.previousElementSibling;
            const incrementBtn = input.nextElementSibling;
            
            decrementBtn.addEventListener('click', () => {
                if (input.value > input.min) {
                    input.value = parseInt(input.value) - 1;
                    input.dispatchEvent(new Event('change'));
                }
            });
            
            incrementBtn.addEventListener('click', () => {
                if (input.value < input.max) {
                    input.value = parseInt(input.value) + 1;
                    input.dispatchEvent(new Event('change'));
                }
            });
        });
    }
    
    // Image preview for product forms
    const imageInput = document.getElementById('image');
    const imagePreview = document.getElementById('imagePreview');
    
    if (imageInput && imagePreview) {
        imageInput.addEventListener('change', function() {
            if (this.files && this.files[0]) {
                const reader = new FileReader();
                reader.onload = function(e) {
                    imagePreview.src = e.target.result;
                    imagePreview.classList.remove('d-none');
                    document.getElementById('imagePreviewContainer').classList.remove('d-none');
                }
                reader.readAsDataURL(this.files[0]);
            }
        });
    }
    
    // Auto-dismiss alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
    if (alerts.length > 0) {
        alerts.forEach(alert => {
            setTimeout(() => {
                const bsAlert = new bootstrap.Alert(alert);
                bsAlert.close();
            }, 5000);
        });
    }
    
    // Confirm deletion of resources
    const confirmButtons = document.querySelectorAll('.confirm-delete');
    if (confirmButtons.length > 0) {
        confirmButtons.forEach(button => {
            button.addEventListener('click', function(e) {
                if (!confirm('Are you sure you want to delete this item? This action cannot be undone.')) {
                    e.preventDefault();
                }
            });
        });
    }
    
    // Print functionality
    const printButtons = document.querySelectorAll('.btn-print');
    if (printButtons.length > 0) {
        printButtons.forEach(button => {
            button.addEventListener('click', function() {
                window.print();
            });
        });
    }
    
    // Check/uncheck all checkboxes
    const selectAllCheckbox = document.getElementById('selectAll');
    if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener('change', function() {
            const checkboxes = document.querySelectorAll('input[name="selected_items[]"]');
            checkboxes.forEach(checkbox => {
                checkbox.checked = selectAllCheckbox.checked;
            });
        });
    }
});